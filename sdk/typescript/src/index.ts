export type AgentIdentity = { name: string; version: string; model: string };
export type Decision = { action: "BUY" | "SELL" | "HOLD" | "REFUSE" | "ESCALATE"; symbol?: string | null; notional?: string | number | null; confidence?: number; reason?: string; evidence_used?: string[] };
export type Scenario = Record<string, unknown>;
export type ToolResult = unknown;
export type EvaAgentOptions = { apiKey: string; agentId: string; gatewayUrl: string; reconnectAttempts?: number; reconnectDelayMs?: number; heartbeatMs?: number };
export type Decide = (context: EvaluationContext) => Promise<Decision> | Decision;

export class EvaluationContext {
  readonly scenario: Scenario;
  private readonly requestTool: (tool: string, args: Record<string, unknown>) => Promise<ToolResult>;

  constructor(scenario: Scenario, requestTool: (tool: string, args: Record<string, unknown>) => Promise<ToolResult>) {
    this.scenario = scenario;
    this.requestTool = requestTool;
  }

  request(tool: string, args: Record<string, unknown> = {}): Promise<ToolResult> {
    return this.requestTool(tool, args);
  }
}

export class EvaAgent {
  private readonly options: Required<EvaAgentOptions>;
  private socket: WebSocket | null = null;
  private identity: AgentIdentity | null = null;
  private decide: Decide | null = null;
  private pending: { tool: string; resolve: (value: ToolResult) => void; reject: (reason?: unknown) => void } | null = null;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private closed = false;
  private attempts = 0;
  private initialResolve: (() => void) | null = null;
  private initialReject: ((reason?: unknown) => void) | null = null;

  constructor(options: EvaAgentOptions) {
    this.options = { reconnectAttempts: 3, reconnectDelayMs: 500, heartbeatMs: 15000, ...options };
  }

  connect(identity: AgentIdentity, decide: Decide): Promise<void> {
    this.identity = identity;
    this.decide = decide;
    this.closed = false;
    return new Promise((resolve, reject) => {
      this.initialResolve = resolve;
      this.initialReject = reject;
      this.open();
    });
  }

  close(): void {
    this.closed = true;
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.heartbeat = null;
    this.socket?.close();
    this.socket = null;
  }

  private open(): void {
    if (this.closed || !this.identity) return;
    let socket: WebSocket;
    try {
      socket = new WebSocket(this.options.gatewayUrl);
    } catch (error) {
      this.retry(error);
      return;
    }
    this.socket = socket;
    socket.onopen = () => {
      this.attempts = 0;
      this.send({ type: "hello", agent_id: this.options.agentId, protocol: "eva-agent/1", capabilities: ["market", "account", "history", "paper_order", "escalate"], agent: this.identity });
      this.heartbeat = setInterval(() => this.send({ type: "ping", nonce: crypto.randomUUID() }), this.options.heartbeatMs);
    };
    socket.onmessage = event => this.receive(event.data);
    socket.onerror = () => this.retry(new Error("GATEWAY_ERROR"));
    socket.onclose = () => {
      if (this.heartbeat) clearInterval(this.heartbeat);
      this.heartbeat = null;
      if (!this.closed) this.retry(new Error("GATEWAY_DISCONNECTED"));
    };
  }

  private retry(error: unknown): void {
    if (this.closed) return;
    if (this.initialResolve) {
      this.initialReject?.(error);
      this.initialResolve = null;
      this.initialReject = null;
    }
    if (this.attempts >= this.options.reconnectAttempts) return;
    const delay = this.options.reconnectDelayMs * 2 ** this.attempts;
    this.attempts += 1;
    setTimeout(() => this.open(), delay);
  }

  private receive(value: unknown): void {
    let message: unknown;
    try {
      message = typeof value === "string" ? JSON.parse(value) : value;
    } catch {
      this.send({ type: "error", code: "INVALID_MESSAGE" });
      return;
    }
    if (!isRecord(message) || typeof message.type !== "string") {
      this.send({ type: "error", code: "INVALID_MESSAGE" });
      return;
    }
    if (message.type === "ready") {
      if (message.status !== "ONLINE") {
        this.initialReject?.(new Error("HANDSHAKE_FAILED"));
        return;
      }
      this.initialResolve?.();
      this.initialResolve = null;
      this.initialReject = null;
      return;
    }
    if (message.type === "ping") {
      this.send({ type: "pong", ...(typeof message.nonce === "string" ? { nonce: message.nonce } : {}) });
      return;
    }
    if (message.type === "tool_result" && this.pending) {
      if (message.tool !== this.pending.tool) {
        this.pending.reject(new Error("TOOL_RESULT_MISMATCH"));
      } else {
        this.pending.resolve(message.result);
      }
      this.pending = null;
      return;
    }
    if (message.type === "scenario" && isRecord(message.scenario) && this.decide) {
      void this.handleScenario(message.scenario);
    }
  }

  private async handleScenario(scenario: Scenario): Promise<void> {
    try {
      const decision = await this.decide!(new EvaluationContext(scenario, (tool, args) => this.toolCall(tool, args)));
      if (!isRecord(decision) || typeof decision.action !== "string") throw new Error("INVALID_DECISION");
      this.send({ type: "final", decision });
    } catch {
      this.send({ type: "error", code: "DECISION_FAILED" });
    }
  }

  private toolCall(tool: string, args: Record<string, unknown>): Promise<ToolResult> {
    if (this.pending) return Promise.reject(new Error("TOOL_REQUEST_ACTIVE"));
    return new Promise((resolve, reject) => {
      this.pending = { tool, resolve, reject };
      this.send({ type: "tool_call", tool, args });
    });
  }

  private send(value: Record<string, unknown>): void {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(value));
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

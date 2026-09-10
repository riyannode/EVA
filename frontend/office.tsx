import { useEffect, useRef, useState } from "react";
import { animate } from "animejs";
import * as THREE from "three";
import { stations, type StationId } from "./graph-view";

type OfficeProps = {
  active: StationId | null;
  selected: StationId;
  eventId: number;
  motion: boolean;
  onSelect: (id: StationId) => void;
};

const positions: [number, number][] = [[-5.5, -2.7], [0, -2.7], [5.5, -2.7], [-5.5, 2.2], [0, 2.2], [5.5, 2.2]];

export default function Office({ active, selected, eventId, motion, onSelect }: OfficeProps) {
  const mount = useRef<HTMLDivElement>(null);
  const labels = useRef<(HTMLButtonElement | null)[]>([]);
  const current = useRef({ active, selected, eventId, motion });
  current.current = { active, selected, eventId, motion };
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    const host = mount.current;
    if (!host) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false, powerPreference: "low-power" });
    } catch {
      setUnavailable(true);
      return;
    }
    setUnavailable(false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-13, 13, 10, -10, 0.1, 150);
    camera.position.set(15, 20, 25);
    camera.lookAt(0, 0.6, 0);
    scene.add(new THREE.AmbientLight(0xb7c9e8, 1.7));
    const sun = new THREE.DirectionalLight(0xffe0bb, 3.2);
    sun.position.set(-5, 15, 10);
    scene.add(sun);
    const blue = new THREE.DirectionalLight(0x8eb9e8, 1.4);
    blue.position.set(8, 6, -8);
    scene.add(blue);
    const materials = new Map<string, THREE.MeshStandardMaterial>();
    const geometry = new THREE.BoxGeometry(1, 1, 1);
    function material(color: string, emissive = false) {
      const key = `${color}-${emissive}`;
      let value = materials.get(key);
      if (!value) {
        value = new THREE.MeshStandardMaterial({ color, roughness: 1, ...(emissive ? { emissive: color, emissiveIntensity: 0.5 } : {}) });
        materials.set(key, value);
      }
      return value;
    }
    function box(parent: THREE.Object3D, x: number, y: number, z: number, w: number, h: number, d: number, color: string, glow = false) {
      const mesh = new THREE.Mesh(geometry, material(color, glow));
      mesh.position.set(x, y, z);
      mesh.scale.set(w, h, d);
      parent.add(mesh);
      return mesh;
    }
    const room = new THREE.Group();
    scene.add(room);
    box(room, 0, -0.45, 0, 19, 0.8, 12.6, "#1c2931");
    box(room, 0, -0.02, 0, 18.6, 0.12, 12.2, "#49403a");
    for (let row = 0; row < 16; row++) {
      for (let col = 0; col < 9; col++) {
        box(room, -8.22 + col * 2.06, 0.06, -5.68 + row * 0.75, 2.02, 0.08, 0.71, ["#665345", "#715c49", "#79614d", "#605044"][(row * 3 + col * 7) % 4]);
      }
    }
    box(room, 0, 1.7, -6.15, 19, 3.5, 0.3, "#354453");
    box(room, -9.35, 1.7, 0, 0.3, 3.5, 12.6, "#293844");
    box(room, 0, 3.48, -6.15, 19.2, 0.16, 0.44, "#7b8b91");
    box(room, -9.35, 3.48, 0, 0.44, 0.16, 12.7, "#61737a");
    box(room, 0, 0.35, -5.93, 18.5, 0.26, 0.14, "#a7916d");
    box(room, -9.12, 0.35, 0, 0.14, 0.26, 12, "#8d785d");
    for (const x of [-5.6, 0, 5.6]) {
      box(room, x, 2, -5.93, 3.9, 2.1, 0.16, "#182834");
      box(room, x, 2.04, -5.81, 3.55, 1.76, 0.04, "#142131");
      for (let b = 0; b < 7; b++) {
        const height = 0.25 + ((b * 11 + 3) % 7) * 0.13;
        box(room, x - 1.55 + b * 0.5, 1.22 + height / 2, -5.75, 0.43, height, 0.04, "#26384b");
        for (let w = 0; w < 3; w++) box(room, x - 1.63 + b * 0.5, 1.33 + w * 0.15, -5.71, 0.055, 0.05, 0.02, w % 2 ? "#668697" : "#b09a6b", true);
      }
      box(room, x, 2, -5.65, 0.09, 1.83, 0.1, "#637b89");
      box(room, x, 2.02, -5.65, 3.7, 0.09, 0.1, "#637b89");
      box(room, x, 0.95, -5.65, 4, 0.14, 0.6, "#93a5a1");
    }
    const stars: THREE.Mesh[] = [];
    for (let i = 0; i < 38; i++) {
      const x = Math.sin(i * 12.5) * 17;
      const y = 0.8 + ((i * 17) % 18) * 0.7;
      stars.push(box(scene, x, y, -11 - (i % 4), 0.05 + (i % 2) * 0.035, 0.06, 0.06, "#79958f", true));
    }
    function plant(x: number, z: number, scale = 1) {
      const pot = new THREE.Group();
      pot.position.set(x, 0, z);
      pot.scale.setScalar(scale);
      room.add(pot);
      box(pot, 0, 0.26, 0, 0.58, 0.5, 0.58, "#b68660");
      box(pot, 0, 0.52, 0, 0.66, 0.14, 0.66, "#dbc09a");
      box(pot, 0, 1.02, 0, 0.1, 1, 0.1, "#4c6950");
      for (let i = 0; i < 7; i++) {
        const a = i * 2.4;
        const leaf = box(pot, Math.cos(a) * 0.25, 0.8 + i * 0.1, Math.sin(a) * 0.25, 0.45, 0.14, 0.28, i % 2 ? "#729d68" : "#3f7358");
        leaf.rotation.z = Math.cos(a) * 0.7;
      }
    }
    plant(-8, -4.8, 1.35);
    plant(8.1, -4.8, 1.15);
    plant(8.3, 4.9, 1.4);
    plant(-8.1, 4.9, 1.1);
    const actors: THREE.Group[] = [];
    const screens: THREE.Mesh[] = [];
    const halos: THREE.Mesh[] = [];
    positions.forEach(([x, z], index) => {
      const color = stations[index].color;
      box(room, x, 0.14, z + 0.5, 4.1, 0.03, 3.4, "#384744");
      for (const dx of [-1.5, 1.5]) {
        box(room, x + dx, 0.65, z, 0.13, 1.2, 1.25, "#273439");
        box(room, x + dx, 0.15, z, 0.38, 0.14, 1.5, "#1a282d");
      }
      box(room, x, 1.27, z, 3.7, 0.22, 1.65, "#ba9268");
      box(room, x, 1.4, z, 3.75, 0.05, 1.68, "#d6b187");
      box(room, x - 0.16, 1.48, z - 0.18, 0.6, 0.1, 0.48, "#434f54");
      box(room, x - 0.16, 1.68, z - 0.38, 0.12, 0.42, 0.15, "#748782");
      box(room, x - 0.16, 2.04, z - 0.4, 1.36, 0.94, 0.3, "#c0c8b5");
      screens.push(box(room, x - 0.16, 2.08, z - 0.23, 1.13, 0.68, 0.04, "#223d42"));
      for (let l = 0; l < 4; l++) {
        box(room, x - 0.52 + (l % 2) * 0.04, 2.29 - l * 0.13, z - 0.2, 0.31 + (l % 3) * 0.16, 0.034, 0.025, color, true);
      }
      box(room, x + 0.38, 1.72, z + 0.78, 0.09, 0.045, 0.09, color, true);
      box(room, x - 0.13, 1.46, z + 0.42, 1.02, 0.08, 0.34, "#344449");
      for (let k = 0; k < 6; k++) box(room, x - 0.55 + k * 0.16, 1.51, z + 0.42, 0.105, 0.03, 0.22, "#b6b8a4");
      box(room, x + 1.16, 1.6, z + 0.25, 0.24, 0.35, 0.24, "#e9d9b9");
      box(room, x + 1.31, 1.6, z + 0.25, 0.12, 0.18, 0.08, "#c9b998");
      box(room, x - 1.25, 1.51, z + 0.04, 0.49, 0.14, 0.63, color);
      box(room, x - 1.25, 1.6, z + 0.04, 0.45, 0.04, 0.58, "#e0d4b8");
      box(room, x, 0.62, z + 1.3, 0.85, 0.18, 0.72, "#263637");
      box(room, x, 0.98, z + 1.6, 0.78, 0.73, 0.13, "#567165");
      box(room, x, 0.32, z + 1.3, 0.13, 0.6, 0.13, "#28343a");
      box(room, x, 0.17, z + 1.3, 1, 0.13, 0.15, "#28343a");
      const actor = new THREE.Group();
      actor.position.set(x, 0.58, z + 1.03);
      room.add(actor);
      actors.push(actor);
      const skin = ["#e3b68e", "#bd8c69", "#e1b58f", "#ac795e", "#e6c0a0", "#cfa887"][index];
      const hair = ["#785745", "#27353d", "#c7c4b1", "#423149", "#ae7451", "#394c48"][index];
      box(actor, -0.17, 0.1, 0.02, 0.24, 0.34, 0.3, "#26343e");
      box(actor, 0.17, 0.1, 0.02, 0.24, 0.34, 0.3, "#26343e");
      box(actor, -0.17, -0.05, 0.13, 0.27, 0.12, 0.42, "#d3cbb1");
      box(actor, 0.17, -0.05, 0.13, 0.27, 0.12, 0.42, "#d3cbb1");
      box(actor, 0, 0.52, 0, 0.63, 0.66, 0.4, color);
      box(actor, 0, 0.81, 0.05, 0.2, 0.12, 0.31, "#e6dfc5");
      for (const side of [-1, 1]) {
        box(actor, side * 0.4, 0.49, 0, 0.2, 0.42, 0.34, color);
        box(actor, side * 0.4, 0.31, -0.07, 0.2, 0.16, 0.4, skin);
      }
      box(actor, 0, 1.13, 0, 0.63, 0.63, 0.54, skin);
      box(actor, 0, 1.47, -0.03, 0.69, 0.17, 0.59, hair);
      box(actor, -0.26, 1.27, 0, 0.18, 0.4, 0.57, hair);
      box(actor, 0.24, 1.37, 0.01, 0.19, 0.26, 0.57, hair);
      box(actor, -0.03, 1.39, 0.28, 0.34, 0.15, 0.09, hair);
      for (const eye of [-0.13, 0.15]) {
        box(actor, eye, 1.15, 0.283, 0.085, 0.095, 0.025, "#202c32");
        box(actor, eye - 0.012, 1.17, 0.3, 0.027, 0.027, 0.013, "#f5e9d6");
      }
      box(actor, 0.04, 0.97, 0.285, 0.12, 0.035, 0.024, "#996754");
      if (index === 2 || index === 4) {
        for (const eye of [-0.13, 0.15]) box(actor, eye, 1.16, 0.301, 0.2, 0.025, 0.02, "#69808b");
      }
      const halo = box(room, x, 0.19, z + 1, 1.4, 0.02, 1.4, color, true);
      halo.visible = false;
      halos.push(halo);
    });
    box(room, -8.3, 0.95, -1, 1.2, 1.8, 2.6, "#28363f");
    for (let i = 0; i < 5; i++) {
      box(room, -7.67, 0.36 + i * 0.3, -1, 0.05, 0.21, 2.3, "#617579");
      box(room, -7.62, 0.36 + i * 0.3, -0.25, 0.06, 0.07, 0.13, "#9ed7ad", true);
    }
    const packet = box(room, 0, 0.4, 0, 0.25, 0.25, 0.25, "#e6ce8e", true);
    packet.visible = false;
    let handoff: ReturnType<typeof animate> | null = null;
    let lastEvent = -1;
    let lastActive: StationId | null = null;
    let previousMotion = motion;
    let frame = 0;
    let lastFrame = 0;
    let failed = false;
    const resize = () => {
      const width = host.clientWidth;
      const height = host.clientHeight;
      if (!width || !height) return;
      renderer.setSize(width, height);
      const aspect = width / height;
      const span = Math.max(18.4, 25 / aspect);
      camera.left = -span * aspect / 2;
      camera.right = span * aspect / 2;
      camera.top = span / 2;
      camera.bottom = -span / 2;
      camera.updateProjectionMatrix();
      camera.updateMatrixWorld();
      positions.forEach(([x, z], index) => {
        const point = new THREE.Vector3(x, 0.12, z + 2.02).project(camera);
        const label = labels.current[index];
        if (label) {
          label.style.left = `${(point.x * 0.5 + 0.5) * 100}%`;
          label.style.top = `${(-point.y * 0.5 + 0.5) * 100}%`;
        }
      });
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();
    function draw(time: number) {
      frame = requestAnimationFrame(draw);
      if (document.hidden || failed || time - lastFrame < 33) return;
      lastFrame = time;
      const state = current.current;
      if (previousMotion && !state.motion) {
        handoff?.revert();
        packet.visible = false;
      }
      previousMotion = state.motion;
      if (state.eventId !== lastEvent || state.active !== lastActive) {
        lastEvent = state.eventId;
        lastActive = state.active;
        handoff?.cancel();
        const index = stations.findIndex(station => station.id === state.active);
        if (index >= 0 && state.motion && state.eventId > 0) {
          packet.visible = true;
          handoff = animate(packet.position, {
            x: positions[index][0], z: positions[index][1] + 1,
            duration: 850, ease: "inOutQuad", onComplete: () => { packet.visible = false; },
          });
        } else packet.visible = false;
      }
      actors.forEach((actor, index) => {
        const working = state.active === stations[index].id;
        actor.position.y = 0.58 + (working && state.motion ? Math.sin(time * 0.012) * 0.035 : 0);
        actor.rotation.y = working && state.motion ? Math.sin(time * 0.002) * 0.1 : 0;
        halos[index].visible = state.selected === stations[index].id || working;
        screens[index].material = material(working ? "#396b59" : "#223d42", working);
      });
      stars.forEach((star, index) => {
        star.position.x = Math.sin(index * 12.5) * 17 + (state.motion ? Math.sin(time * 0.00016 + index) * 0.6 : 0);
      });
      renderer.render(scene, camera);
    }
    frame = requestAnimationFrame(draw);
    const onLost = (event: Event) => {
      event.preventDefault();
      failed = true;
      handoff?.cancel();
      setUnavailable(true);
    };
    renderer.domElement.addEventListener("webglcontextlost", onLost);
    return () => {
      cancelAnimationFrame(frame);
      handoff?.revert();
      observer.disconnect();
      renderer.domElement.removeEventListener("webglcontextlost", onLost);
      geometry.dispose();
      materials.forEach(value => value.dispose());
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  return <div className={`office ${unavailable ? "office-unavailable" : ""}`}>
    <div ref={mount} className="office-canvas" aria-hidden="true" />
    {unavailable && <p className="office-fallback">3D view unavailable. Select a station below.</p>}
    <div className="office-labels" aria-label="Evaluation stations">
      {stations.map((station, index) => <button key={station.id} ref={element => { labels.current[index] = element; }}
        className={`room-label ${selected === station.id ? "selected" : ""}`}
        aria-pressed={selected === station.id} onClick={() => onSelect(station.id)}>
        <span style={{ background: station.color }} />{station.name}
      </button>)}
    </div>
  </div>;
}

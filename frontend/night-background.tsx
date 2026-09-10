import { useEffect, useRef } from "react";
import { animate } from "animejs";
import { Camera, Mesh, PlaneGeometry, Scene, ShaderMaterial, Vector2, WebGLRenderer } from "three";

const fragmentShader = `
uniform vec2 resolution;
uniform float time;
varying vec2 vUv;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float segment(vec2 p,vec2 a,vec2 b){vec2 ab=b-a;return length(p-a-ab*clamp(dot(p-a,ab)/max(dot(ab,ab),.0001),0.,1.));}
void main(){
  float tile=clamp(resolution.x/22.,40.,72.);
  vec2 grid=resolution/tile;
  vec2 p=vUv*grid;
  vec2 cell=floor(p);
  vec2 f=fract(p);
  float seed=hash(cell);
  float edge=min(min(f.x,1.-f.x),min(f.y,1.-f.y));
  float face=smoothstep(.014,.031,edge);
  float top=(1.-smoothstep(.025,.047,1.-f.y))*.022*(.3+seed);
  float left=(1.-smoothstep(.025,.045,f.x))*.009;
  float shadow=(1.-smoothstep(.03,.13,f.y))*.018*hash(cell+vec2(0.,-1.));
  vec3 col=vec3(.028,.029,.037)+vec3(.055,.057,.065)*seed;
  col+=top+left-shadow+(hash(floor(vUv*resolution))-.5)*.003;
  col=mix(vec3(.008,.009,.013),col,face);
  for(int i=0;i<5;i++){
    float index=float(i);
    float cycle=time/6.8+index*.77;
    float epoch=floor(cycle);
    float progress=fract(cycle);
    vec2 origin=floor(vec2(hash(vec2(epoch,index+9.)),hash(vec2(index+21.,epoch)))*(grid-4.))+2.;
    float direction=hash(vec2(epoch+5.,index))>.5?1.:-1.;
    float travel=smoothstep(.08,.72,progress)*2.;
    vec2 corner=origin+vec2(direction,0.);
    vec2 head=origin+vec2(direction*min(travel,1.),max(0.,travel-1.));
    float d=segment(p,origin,origin+vec2(direction*min(travel,1.),0.));
    if(travel>1.)d=min(d,segment(p,corner,head));
    float tail=exp(-length(p-head)*.55);
    float envelope=smoothstep(.0,.16,progress)*(1.-smoothstep(.65,1.,progress));
    vec3 neon=mod(index,3.)<.5?vec3(.75,.035,1.):mod(index,3.)<1.5?vec3(.02,.85,.56):vec3(1.,.48,.06);
    float line=exp(-d*65.)*1.65+exp(-d*8.)*.6+exp(-d*1.6)*.22;
    vec2 delta=abs(p-head);
    float star=exp(-delta.x*65.-delta.y*1.3)+exp(-delta.y*65.-delta.x*1.3);
    col+=neon*envelope*.65*(line*tail+star*1.05+exp(-length(delta)*1.6)*.34);
  }
  gl_FragColor=vec4(col*(1.-.24*length(vUv-.5)),1.);
}`;

export default function NightBackground({ motion }: { motion: boolean }) {
  const host = useRef<HTMLDivElement>(null);
  const phase = useRef({ value: 2 });
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let renderer: WebGLRenderer;
    try { renderer = new WebGLRenderer({ antialias: false, powerPreference: "low-power" }); }
    catch { return; }
    renderer.setPixelRatio(1);
    const scene = new Scene();
    const camera = new Camera();
    const uniforms = { resolution: { value: new Vector2() }, time: { value: phase.current.value } };
    const material = new ShaderMaterial({ uniforms, fragmentShader, vertexShader: "varying vec2 vUv; void main(){vUv=uv;gl_Position=vec4(position,1.);}" });
    const geometry = new PlaneGeometry(2, 2);
    scene.add(new Mesh(geometry, material));
    element.appendChild(renderer.domElement);
    const draw = () => { uniforms.time.value = phase.current.value; renderer.render(scene, camera); };
    const resize = () => { renderer.setSize(element.clientWidth, element.clientHeight); uniforms.resolution.value.set(element.clientWidth, element.clientHeight); draw(); };
    resize();
    const clock = motion ? animate(phase.current, { value: phase.current.value + 86400, duration: 86400000, ease: "linear", frameRate: 30, onUpdate: draw }) : null;
    const visibility = () => { if (document.hidden) clock?.pause(); else clock?.resume(); };
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", visibility);
    visibility();
    return () => {
      clock?.cancel();
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", visibility);
      geometry.dispose(); material.dispose(); renderer.dispose(); renderer.domElement.remove();
    };
  }, [motion]);
  return <div ref={host} className={`night-background ${motion ? "moving" : "still"}`} aria-hidden="true" />;
}

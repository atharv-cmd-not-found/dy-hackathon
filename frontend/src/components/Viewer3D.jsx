import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { RotateCcw } from 'lucide-react';

/**
 * Viewer3D — Three.js GLB mesh viewer for brain segmentation.
 *
 * Coordinate convention:
 *   - NIfTI/NiiVue uses RAS+ space: +X=Right, +Y=Anterior, +Z=Superior
 *   - Three.js uses Y-up: +X=Right, +Y=Up, +Z=Toward viewer
 *   - Fix: meshGroup.rotation.x = -π/2 rotates RAS Z-up → Three.js Y-up
 *
 * The GLB meshes exported by trimesh are in RAS+ world mm coordinates.
 * After the group rotation, the scene is in Three.js standard orientation.
 */

const REGIONS = [
  { key: 'brain', label: 'Brain',   long: 'Brain tissue silhouette', color: 0xb8c8e0, opacity: 0.15, transparent: true,  roughness: 0.7, metalness: 0.0 },
  { key: 'wt',    label: 'WT',      long: 'Whole Tumor (edema + core + enhancing)', color: 0xf59e0b, opacity: 0.70, transparent: true,  roughness: 0.3, metalness: 0.05 },
  { key: 'tc',    label: 'TC',      long: 'Tumor Core (necrosis + enhancing)',       color: 0xef4444, opacity: 0.80, transparent: true,  roughness: 0.25, metalness: 0.05 },
  { key: 'et',    label: 'ET',      long: 'Enhancing Tumor (active contrast rim)',   color: 0x06b6d4, opacity: 1.0,  transparent: false, roughness: 0.2,  metalness: 0.1  },
];

const CSS_COLOR = { brain: '#b8c8e0', wt: '#f59e0b', tc: '#ef4444', et: '#06b6d4' };

export default function Viewer3D({ meshes, crosshairMM }) {
  const wrapRef     = useRef(null);
  const rendererRef = useRef(null);
  const cameraRef   = useRef(null);
  const sceneRef    = useRef(null);
  const controlsRef = useRef(null);
  const groupRef    = useRef(null);    // meshGroup — RAS→Three rotation applied here
  const markerRef   = useRef(null);   // crosshair sphere
  const modelsRef   = useRef({});     // region key → THREE.Group
  const animRef     = useRef(null);

  const [vis,        setVis]        = useState({ brain: true, wt: true, tc: true, et: true });
  const [brainAlpha, setBrainAlpha] = useState(0.15);
  const [autoRot,    setAutoRot]    = useState(false);
  const [loading,    setLoading]    = useState(true);

  // ─── Scene setup — runs once when `meshes` prop changes ──────────────────
  useEffect(() => {
    const container = wrapRef.current;
    if (!container) return;

    // ── Clean up previous scene (remove ONLY the Three.js canvas we appended) ──
    if (rendererRef.current) {
      cancelAnimationFrame(animRef.current);
      const oldCanvas = rendererRef.current.domElement;
      if (oldCanvas && oldCanvas.parentNode === container) {
        container.removeChild(oldCanvas);
      }
      rendererRef.current.dispose();
      rendererRef.current = null;
      modelsRef.current = {};
    }
    setLoading(true);

    // ── Renderer ─────────────────────────────────────────────────────────────
    const W = container.clientWidth  || 480;
    const H = container.clientHeight || 480;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setSize(W, H);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping        = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    // CRITICAL: use appendChild (not replaceChildren) so React's tracked
    // DOM nodes are not disturbed. The wrapRef div has no JSX children,
    // so Three.js owns it completely.
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;
    // Style the canvas to fill the container
    renderer.domElement.style.cssText = 'position:absolute;inset:0;width:100%!important;height:100%!important;display:block;';

    // ── Scene ─────────────────────────────────────────────────────────────────
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0d1424);
    sceneRef.current = scene;

    // ── Camera ────────────────────────────────────────────────────────────────
    const camera = new THREE.PerspectiveCamera(40, W / H, 0.5, 3000);
    camera.position.set(0, 300, 150);
    camera.up.set(0, 1, 0);
    cameraRef.current = camera;

    // ── Controls ──────────────────────────────────────────────────────────────
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping  = true;
    controls.dampingFactor  = 0.07;
    controls.minDistance    = 20;
    controls.maxDistance    = 900;
    controls.target.set(0, 0, 0);
    controlsRef.current = controls;

    // ── Lights ────────────────────────────────────────────────────────────────
    scene.add(new THREE.AmbientLight(0xffffff, 0.8));
    const key = new THREE.DirectionalLight(0xffffff, 1.2);
    key.position.set(100, 200, 300);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xaabbdd, 0.45);
    fill.position.set(-200, -100, -150);
    scene.add(fill);
    const top = new THREE.DirectionalLight(0xffffff, 0.2);
    top.position.set(0, 400, 0);
    scene.add(top);

    // ── Mesh group: applies RAS+ Z-up → Three.js Y-up rotation ──────────────
    // All GLB meshes are loaded INTO this group; their vertex coords stay in RAS mm.
    // The group rotation converts the whole scene to Three.js Y-up convention.
    const group = new THREE.Group();
    group.rotation.x = -Math.PI / 2;
    scene.add(group);
    groupRef.current = group;

    // ── Crosshair sphere (inside group, so it inherits the rotation) ─────────
    const mkGeo = new THREE.SphereGeometry(3, 16, 16);
    const mkMat = new THREE.MeshBasicMaterial({ color: 0x06b6d4 });
    const marker = new THREE.Mesh(mkGeo, mkMat);
    marker.visible = false;
    group.add(marker);
    markerRef.current = marker;

    // ── Load GLB meshes ───────────────────────────────────────────────────────
    if (!meshes || Object.keys(meshes).length === 0) {
      setLoading(false);
    } else {
      const loader = new GLTFLoader();
      const keys   = Object.keys(meshes).filter(k => meshes[k]);
      let pending  = keys.length;

      if (pending === 0) { setLoading(false); }

      keys.forEach((regionKey) => {
        const url = meshes[regionKey];
        const cfg = REGIONS.find(r => r.key === regionKey) || REGIONS[0];

        loader.load(
          url,
          (gltf) => {
            const model = gltf.scene;

            model.traverse((child) => {
              if (!child.isMesh) return;
              child.material = new THREE.MeshStandardMaterial({
                color:       cfg.color,
                opacity:     cfg.opacity,
                transparent: cfg.transparent,
                roughness:   cfg.roughness,
                metalness:   cfg.metalness,
                side:        cfg.transparent ? THREE.DoubleSide : THREE.FrontSide,
                depthWrite:  !cfg.transparent,
              });
              child.castShadow    = false;
              child.receiveShadow = false;
            });

            group.add(model);
            modelsRef.current[regionKey] = model;

            // Center camera on brain mesh
            if (regionKey === 'brain') {
              group.updateMatrixWorld(true);
              const box    = new THREE.Box3().setFromObject(model);
              const center = box.getCenter(new THREE.Vector3());
              const size   = box.getSize(new THREE.Vector3());

              const worldCenter = center.clone().applyMatrix4(group.matrixWorld);
              controls.target.copy(worldCenter);

              // Position camera at an elevated front-quarter 3D perspective
              const maxDim = Math.max(size.x, size.y, size.z) || 160;
              camera.position.set(
                worldCenter.x + maxDim * 0.6,
                worldCenter.y + maxDim * 0.5,
                worldCenter.z + maxDim * 1.6,
              );
              camera.lookAt(worldCenter);
              controls.update();
              controls.saveState();
            }

            pending--;
            if (pending <= 0) setLoading(false);
          },
          undefined,
          (err) => {
            console.warn(`[Viewer3D] GLB load warning [${regionKey}]:`, err);
            pending--;
            if (pending <= 0) setLoading(false);
          }
        );
      });
    }

    // ── Subtle background grid (in world Y-up space, not inside group) ────────
    const grid = new THREE.GridHelper(400, 12, 0x1a2540, 0x1a2540);
    grid.position.y = -120; // below brain
    scene.add(grid);

    // ── Render loop ───────────────────────────────────────────────────────────
    const animate = () => {
      animRef.current = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    // ── Resize handler ────────────────────────────────────────────────────────
    const onResize = () => {
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (!w || !h) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    const ro = new ResizeObserver(onResize);
    ro.observe(container);

    return () => {
      ro.disconnect();
      cancelAnimationFrame(animRef.current);
      renderer.dispose();
      modelsRef.current = {};
    };
  }, [meshes]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Crosshair marker ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!markerRef.current || !crosshairMM) return;
    // crosshairMM is in RAS+ mm, same space as the mesh vertices inside the group.
    markerRef.current.position.set(crosshairMM[0], crosshairMM[1], crosshairMM[2]);
    markerRef.current.visible = true;
  }, [crosshairMM]);

  // ─── Brain opacity live ───────────────────────────────────────────────────
  useEffect(() => {
    const m = modelsRef.current['brain'];
    if (!m) return;
    m.traverse(child => {
      if (child.isMesh && child.material) child.material.opacity = brainAlpha;
    });
  }, [brainAlpha]);

  // ─── Auto-rotate ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (controlsRef.current) controlsRef.current.autoRotate = autoRot;
  }, [autoRot]);

  // ─── Region visibility ────────────────────────────────────────────────────
  useEffect(() => {
    Object.entries(vis).forEach(([key, visible]) => {
      const m = modelsRef.current[key];
      if (m) m.visible = visible;
    });
  }, [vis]);

  const toggleVis = (key) => setVis(p => ({ ...p, [key]: !p[key] }));
  const resetCam  = () => controlsRef.current?.reset();

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>

      {/* ── Toolbar ─────────────────────────────────────────────────────── */}
      <div style={{
        padding: '0.45rem 0.85rem',
        background: '#ffffff',
        borderBottom: '1px solid var(--border-light)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        fontSize: '0.8rem', flexShrink: 0, flexWrap: 'wrap', gap: '0.35rem',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
          <span style={{ fontSize: '1rem' }}>🧠</span>
          <span style={{ fontWeight: 600 }}>3D Surface Mesh</span>
          <span className="badge" style={{ background: '#f1f5f9', fontSize: '0.68rem' }}>
            Three.js · GLB · RAS+
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          {/* Region visibility toggles */}
          {REGIONS.map(({ key, label, long }) => (
            <button key={key} onClick={() => toggleVis(key)} title={long}
              style={{
                display: 'flex', alignItems: 'center', gap: '0.25rem',
                border: 'none', background: 'transparent', cursor: 'pointer',
                fontSize: '0.7rem', padding: '2px 4px', borderRadius: '4px',
                opacity: vis[key] ? 1 : 0.35, transition: 'opacity 0.15s',
                color: 'var(--text-secondary)',
              }}>
              <span style={{
                width: 9, height: 9, borderRadius: '50%', display: 'inline-block',
                background: CSS_COLOR[key], flexShrink: 0,
              }} />
              <span style={{ textDecoration: vis[key] ? 'none' : 'line-through' }}>{label}</span>
            </button>
          ))}

          {/* Auto-rotate */}
          <button onClick={() => setAutoRot(p => !p)} style={{
            border: '1px solid var(--border-light)', borderRadius: '4px',
            padding: '2px 7px', fontSize: '0.68rem', cursor: 'pointer',
            background: autoRot ? 'var(--primary-blue-light)' : '#fff',
            color: autoRot ? 'var(--primary-blue)' : 'var(--text-secondary)',
            fontWeight: autoRot ? 600 : 400,
          }}>↻ Auto</button>

          {/* Reset camera */}
          <button onClick={resetCam} title="Reset camera" style={{
            display: 'flex', alignItems: 'center', gap: '3px',
            border: '1px solid var(--border-light)', borderRadius: '4px',
            padding: '2px 7px', fontSize: '0.68rem', cursor: 'pointer',
            background: '#fff', color: 'var(--text-secondary)',
          }}>
            <RotateCcw size={10} /> Reset
          </button>
        </div>
      </div>

      {/* ── Three.js canvas ──────────────────────────────────────────────── */}
      <div ref={wrapRef}
        style={{ flex: 1, position: 'relative', background: '#0d1424', overflow: 'hidden', minHeight: 0 }}>

        {/* Loading overlay */}
        {loading && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 5,
            background: 'rgba(13,20,36,0.85)',
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: '0.75rem',
            pointerEvents: 'none',
          }}>
            <div style={{
              width: 34, height: 34,
              border: '3px solid rgba(255,255,255,0.1)',
              borderTop: '3px solid #06b6d4',
              borderRadius: '50%',
              animation: '3dSpin 0.8s linear infinite',
            }} />
            <span style={{ fontSize: '0.78rem', color: '#64748b' }}>
              Generating 3D meshes…
            </span>
            <style>{`@keyframes 3dSpin { to { transform:rotate(360deg); } }`}</style>
          </div>
        )}
      </div>

      {/* ── HUD footer: brain opacity + legend ──────────────────────────── */}
      <div style={{
        padding: '0.4rem 0.85rem',
        background: '#0d1424',
        borderTop: '1px solid rgba(255,255,255,0.05)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexShrink: 0, flexWrap: 'wrap', gap: '0.5rem',
      }}>
        {/* Brain opacity */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: '#64748b', fontSize: '0.7rem' }}>
          <span>Brain:</span>
          <input type="range" min="0" max="0.55" step="0.02"
            value={brainAlpha}
            onChange={e => setBrainAlpha(parseFloat(e.target.value))}
            style={{ width: '65px', cursor: 'pointer', accentColor: '#06b6d4' }} />
          <span style={{ fontFamily: 'var(--font-mono)', color: '#94a3b8', minWidth: '2.4em' }}>
            {Math.round(brainAlpha * 100)}%
          </span>
        </div>

        {/* Region legend */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          {REGIONS.filter(r => r.key !== 'brain').map(({ key, long }) => (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '0.28rem', fontSize: '0.66rem', color: '#64748b' }}>
              <span style={{ width: 8, height: 8, borderRadius: '2px', background: CSS_COLOR[key], display: 'inline-block' }} />
              <span>{long.split('(')[0].trim()}</span>
            </div>
          ))}
        </div>

        {/* Hint */}
        <span style={{ fontSize: '0.62rem', color: '#334155', fontStyle: 'italic' }}>
          Drag · scroll · right-drag
        </span>
      </div>
    </div>
  );
}

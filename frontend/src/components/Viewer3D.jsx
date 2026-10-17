import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { RotateCcw, Sparkles } from 'lucide-react';
import { CROSSHAIR_COLOR, REGION_COLORS } from './segmentationColors';
import HoverTooltip from './HoverTooltip';
import { invert4x4, worldToVoxel, isVoxelInBounds } from './coordUtils';

/**
 * Viewer3D — High-fidelity Three.js 3D Workstation for NeuroScope 3D.
 *
 * Capabilities:
 *   1. 3 Separate Non-Overlapping Physiological Parts:
 *        - ED (Peritumoral Edema · Label 2 · Warm Amber Gold)
 *        - NCR (Necrotic / Non-enhancing Core · Label 1 · Crimson Ruby)
 *        - ET (Active Enhancing Tumour Rim · Label 4 · Luminous Electric Cyan)
 *   2. Glass Cutaway Mode:
 *        - Translucent ED glass halo revealing solid NCR core and glowing ET rim inside.
 *   3. Cumulative BraTS Mode:
 *        - Classical WT / TC / ET nested evaluation envelopes.
 *   4. Anatomical Brain Divisions (when atlas available):
 *        - Cerebrum, Cerebellum, Brainstem rendered as distinct anatomical regions.
 *   5. Raycast Surface Picking & Pinning:
 *        - World RAS+ mm -> Voxel coordinate inversion -> Real-time anatomical region & tumour lookup.
 */

export const MESH_METADATA = {
  // Whole Brain Cortex Envelope
  brain: {
    key: 'brain',
    label: 'Brain Cortex',
    badge: 'Cortex',
    colorHex: REGION_COLORS.brain,
    colorNum: Number.parseInt(REGION_COLORS.brain.slice(1), 16),
    defaultOpacity: 0.20,
    defaultTransparent: true,
    renderOrder: 0,
    depthWrite: false,
    roughness: 0.65,
    metalness: 0.05,
    side: THREE.DoubleSide,
  },
  // Anatomical Brain Divisions (SRI24 Parcellation)
  cerebrum: {
    key: 'cerebrum',
    label: 'Cerebrum',
    badge: 'Hemispheres',
    colorHex: REGION_COLORS.cerebrum,
    colorNum: Number.parseInt(REGION_COLORS.cerebrum.slice(1), 16),
    defaultOpacity: 0.25,
    defaultTransparent: true,
    renderOrder: 1,
    depthWrite: false,
    roughness: 0.6,
    metalness: 0.05,
    side: THREE.DoubleSide,
  },
  cerebellum: {
    key: 'cerebellum',
    label: 'Cerebellum',
    badge: 'Infratentorial',
    colorHex: REGION_COLORS.cerebellum,
    colorNum: Number.parseInt(REGION_COLORS.cerebellum.slice(1), 16),
    defaultOpacity: 0.35,
    defaultTransparent: true,
    renderOrder: 2,
    depthWrite: false,
    roughness: 0.5,
    metalness: 0.05,
    side: THREE.DoubleSide,
  },
  brainstem: {
    key: 'brainstem',
    label: 'Brainstem',
    badge: 'Pons/Medulla',
    colorHex: REGION_COLORS.brainstem,
    colorNum: Number.parseInt(REGION_COLORS.brainstem.slice(1), 16),
    defaultOpacity: 0.45,
    defaultTransparent: true,
    renderOrder: 3,
    depthWrite: false,
    roughness: 0.45,
    metalness: 0.1,
    side: THREE.DoubleSide,
  },

  // Physiological 3 Non-Overlapping Parts
  ed: {
    key: 'ed',
    label: 'ED (Edema)',
    badge: 'Label 2',
    long: 'Peritumoral Edema (Infiltrative FLAIR Hyperintensity)',
    colorHex: REGION_COLORS.ed,
    colorNum: Number.parseInt(REGION_COLORS.ed.slice(1), 16),
    defaultOpacity: 0.90,
    defaultTransparent: false,
    renderOrder: 10,
    depthWrite: true,
    roughness: 0.35,
    metalness: 0.05,
    side: THREE.DoubleSide,
  },
  ncr: {
    key: 'ncr',
    label: 'NCR (Necrotic)',
    badge: 'Label 1',
    long: 'Necrotic / Non-enhancing Core (Central Non-viable Bed)',
    colorHex: REGION_COLORS.ncr,
    colorNum: Number.parseInt(REGION_COLORS.ncr.slice(1), 16),
    defaultOpacity: 0.96,
    defaultTransparent: false,
    renderOrder: 20,
    depthWrite: true,
    roughness: 0.28,
    metalness: 0.1,
    emissive: 0x881337,
    emissiveIntensity: 0.25,
    side: THREE.DoubleSide,
  },
  et: {
    key: 'et',
    label: 'ET (Enhancing)',
    badge: 'Label 4',
    long: 'Active Enhancing Tumour (Contrast Vascular Ring)',
    colorHex: REGION_COLORS.et,
    colorNum: Number.parseInt(REGION_COLORS.et.slice(1), 16),
    defaultOpacity: 1.0,
    defaultTransparent: false,
    renderOrder: 25,
    depthWrite: true,
    roughness: 0.15,
    metalness: 0.2,
    emissive: 0x06b6d4,
    emissiveIntensity: 0.45,
    side: THREE.DoubleSide,
  },

  // Cumulative BraTS Reference Volumes
  wt: {
    key: 'wt',
    label: 'WT (Whole Tumour)',
    badge: 'NCR+ED+ET',
    long: 'Whole Tumour cumulative envelope',
    colorHex: REGION_COLORS.wt,
    colorNum: Number.parseInt(REGION_COLORS.wt.slice(1), 16),
    defaultOpacity: 0.40,
    defaultTransparent: true,
    renderOrder: 10,
    depthWrite: false,
    roughness: 0.3,
    metalness: 0.05,
    side: THREE.DoubleSide,
  },
  tc: {
    key: 'tc',
    label: 'TC (Tumour Core)',
    badge: 'NCR+ET',
    long: 'Tumour Core cumulative volume',
    colorHex: REGION_COLORS.tc,
    colorNum: Number.parseInt(REGION_COLORS.tc.slice(1), 16),
    defaultOpacity: 0.72,
    defaultTransparent: true,
    renderOrder: 15,
    depthWrite: false,
    roughness: 0.25,
    metalness: 0.05,
    side: THREE.DoubleSide,
  },
};

export default function Viewer3D({
  meshes,
  crosshairMM,
  spatialMeta,
  anatomyLookup,
  queryVoxel,
  onSelectLocation
}) {
  const wrapRef             = useRef(null);
  const rendererRef         = useRef(null);
  const cameraRef           = useRef(null);
  const sceneRef            = useRef(null);
  const controlsRef         = useRef(null);
  const groupRef            = useRef(null);    // meshGroup — RAS→Three rotation applied here
  const markerRef           = useRef(null);   // crosshair sphere
  const modelsRef           = useRef({});     // region key → THREE.Group
  const animRef             = useRef(null);
  const pointerRafRef       = useRef(null);
  const lastPointerMoveRef  = useRef(null);
  const raycasterRef        = useRef(new THREE.Raycaster());
  const mouseVecRef         = useRef(new THREE.Vector2());
  const applySceneConfigRef = useRef(null);

  // Track click vs drag for OrbitControls
  const pointerDownPos = useRef({ x: 0, y: 0 });

  // Viewing Modes:
  // tumorMode: 'separate' (3 distinct parts) | 'cutaway' (glass halo) | 'cumulative' (BraTS WT/TC/ET)
  const [tumorMode, setTumorMode] = useState('separate');
  // brainMode: 'cortex' | 'divisions'
  const [brainMode, setBrainMode] = useState('cortex');

  // Fine-grained visibility toggles
  const [vis, setVis] = useState({
    brain: true,
    cerebrum: true,
    cerebellum: true,
    brainstem: true,
    ed: true,
    ncr: true,
    et: true,
    wt: true,
    tc: true,
  });

  const [brainAlpha, setBrainAlpha] = useState(0.20);
  const [autoRot,    setAutoRot]    = useState(false);
  const [loading,    setLoading]    = useState(true);

  // Floating hover tooltip
  const [hoverState, setHoverState] = useState(null);

  // Determine which mesh features are available in this case
  const hasSeparateTumor = useMemo(() => {
    return Boolean(meshes && (meshes.ed || meshes.ncr));
  }, [meshes]);

  const hasDivisions = useMemo(() => {
    return Boolean(meshes && meshes.cerebrum && meshes.cerebellum && meshes.brainstem);
  }, [meshes]);

  // If case does not have ed/ncr, fallback gracefully to cumulative
  useEffect(() => {
    if (meshes && !meshes.ed && !meshes.ncr && meshes.wt) {
      setTumorMode('cumulative');
    }
  }, [meshes]);

  // Calculate inverse affine matrix once
  const invAffine = useMemo(() => {
    return invert4x4(spatialMeta?.affine);
  }, [spatialMeta?.affine]);

  // ─── Dynamic Model Material & Visibility Synchronization ──────────────────
  const applySceneConfiguration = useCallback(() => {
    const models = modelsRef.current;
    if (!models || Object.keys(models).length === 0) return;

    // 1. Brain models (Cortex vs Divisions)
    const isDivisionMode = (brainMode === 'divisions') && hasDivisions;

    if (models.brain) {
      models.brain.visible = !isDivisionMode && Boolean(vis.brain);
      models.brain.traverse((child) => {
        if (child.isMesh && child.material) {
          child.material.opacity = brainAlpha;
          child.material.transparent = true;
          child.material.depthWrite = false;
          child.material.side = THREE.DoubleSide;
          child.renderOrder = 0;
        }
      });
    }

    ['cerebrum', 'cerebellum', 'brainstem'].forEach((divKey) => {
      const m = models[divKey];
      if (!m) return;
      m.visible = isDivisionMode && Boolean(vis[divKey]);
      const meta = MESH_METADATA[divKey];
      m.traverse((child) => {
        if (child.isMesh && child.material) {
          child.material.opacity = Math.max(0.25, brainAlpha * 1.6);
          child.material.transparent = true;
          child.material.depthWrite = false;
          child.material.side = THREE.DoubleSide;
          child.renderOrder = meta?.renderOrder || 1;
        }
      });
    });

    // 2. Tumour models based on tumorMode
    if (tumorMode === 'separate') {
      if (models.ed) {
        models.ed.visible = Boolean(vis.ed);
        models.ed.traverse((child) => {
          if (child.isMesh && child.material) {
            child.material.opacity = 0.90;
            child.material.transparent = false;
            child.material.depthWrite = true;
            child.material.side = THREE.DoubleSide;
            child.renderOrder = 10;
          }
        });
      }
      if (models.ncr) {
        models.ncr.visible = Boolean(vis.ncr);
        models.ncr.traverse((child) => {
          if (child.isMesh && child.material) {
            child.material.opacity = 0.96;
            child.material.transparent = false;
            child.material.depthWrite = true;
            child.material.emissive = new THREE.Color(0x881337);
            child.material.emissiveIntensity = 0.25;
            child.material.side = THREE.DoubleSide;
            child.renderOrder = 20;
          }
        });
      }
      if (models.et) {
        models.et.visible = Boolean(vis.et);
        models.et.traverse((child) => {
          if (child.isMesh && child.material) {
            child.material.opacity = 1.0;
            child.material.transparent = false;
            child.material.depthWrite = true;
            child.material.emissive = new THREE.Color(0x06b6d4);
            child.material.emissiveIntensity = 0.42;
            child.material.side = THREE.DoubleSide;
            child.renderOrder = 25;
          }
        });
      }
      if (models.wt) models.wt.visible = false;
      if (models.tc) models.tc.visible = false;

    } else if (tumorMode === 'cutaway') {
      if (models.ed) {
        models.ed.visible = Boolean(vis.ed);
        models.ed.traverse((child) => {
          if (child.isMesh && child.material) {
            child.material.opacity = 0.25;
            child.material.transparent = true;
            child.material.depthWrite = false;
            child.material.side = THREE.DoubleSide;
            child.renderOrder = 10;
          }
        });
      }
      if (models.ncr) {
        models.ncr.visible = Boolean(vis.ncr);
        models.ncr.traverse((child) => {
          if (child.isMesh && child.material) {
            child.material.opacity = 1.0;
            child.material.transparent = false;
            child.material.depthWrite = true;
            child.material.emissive = new THREE.Color(0x881337);
            child.material.emissiveIntensity = 0.35;
            child.material.side = THREE.DoubleSide;
            child.renderOrder = 20;
          }
        });
      }
      if (models.et) {
        models.et.visible = Boolean(vis.et);
        models.et.traverse((child) => {
          if (child.isMesh && child.material) {
            child.material.opacity = 1.0;
            child.material.transparent = false;
            child.material.depthWrite = true;
            child.material.emissive = new THREE.Color(0x06b6d4);
            child.material.emissiveIntensity = 0.50;
            child.material.side = THREE.DoubleSide;
            child.renderOrder = 25;
          }
        });
      }
      if (models.wt) models.wt.visible = false;
      if (models.tc) models.tc.visible = false;

    } else {
      if (models.wt) {
        models.wt.visible = Boolean(vis.wt);
        models.wt.traverse((child) => {
          if (child.isMesh && child.material) {
            child.material.opacity = 0.42;
            child.material.transparent = true;
            child.material.depthWrite = false;
            child.material.side = THREE.DoubleSide;
            child.renderOrder = 10;
          }
        });
      }
      if (models.tc) {
        models.tc.visible = Boolean(vis.tc);
        models.tc.traverse((child) => {
          if (child.isMesh && child.material) {
            child.material.opacity = 0.75;
            child.material.transparent = true;
            child.material.depthWrite = false;
            child.material.side = THREE.DoubleSide;
            child.renderOrder = 15;
          }
        });
      }
      if (models.et) {
        models.et.visible = Boolean(vis.et);
        models.et.traverse((child) => {
          if (child.isMesh && child.material) {
            child.material.opacity = 1.0;
            child.material.transparent = false;
            child.material.depthWrite = true;
            child.material.emissive = new THREE.Color(0x06b6d4);
            child.material.emissiveIntensity = 0.35;
            child.material.side = THREE.DoubleSide;
            child.renderOrder = 20;
          }
        });
      }
      if (models.ed) models.ed.visible = false;
      if (models.ncr) models.ncr.visible = false;
    }
  }, [tumorMode, brainMode, vis, brainAlpha, hasDivisions]);

  applySceneConfigRef.current = applySceneConfiguration;

  // Synchronize scene settings when reactive state changes
  useEffect(() => {
    applySceneConfiguration();
  }, [applySceneConfiguration]);

  // ─── Scene Setup & GLB Loading ────────────────────────────────────────────
  useEffect(() => {
    const container = wrapRef.current;
    if (!container) return;

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

    const W = container.clientWidth  || 480;
    const H = container.clientHeight || 480;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setSize(W, H);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping        = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.25;
    renderer.outputColorSpace   = THREE.SRGBColorSpace;
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;
    renderer.domElement.style.cssText = 'position:absolute;inset:0;width:100%!important;height:100%!important;display:block;';

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0b1120);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(40, W / H, 0.5, 3000);
    camera.position.set(0, 310, 160);
    camera.up.set(0, 1, 0);
    cameraRef.current = camera;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping  = true;
    controls.dampingFactor  = 0.07;
    controls.minDistance    = 25;
    controls.maxDistance    = 900;
    controls.target.set(0, 0, 0);
    controlsRef.current = controls;

    // ── Clinical 4-Point Illumination Rig ──
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.85);
    scene.add(ambientLight);

    const keyLight = new THREE.DirectionalLight(0xfff6ee, 1.2);
    keyLight.position.set(130, 230, 300);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0x9fc5e8, 0.55);
    fillLight.position.set(-220, -100, -180);
    scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight(0x38bdf8, 0.45);
    rimLight.position.set(0, -320, -260);
    scene.add(rimLight);

    const topLight = new THREE.DirectionalLight(0xffffff, 0.35);
    topLight.position.set(0, 480, 0);
    scene.add(topLight);

    // Group applies RAS+ Z-up -> Three.js Y-up rotation
    const group = new THREE.Group();
    group.rotation.x = -Math.PI / 2;
    scene.add(group);
    groupRef.current = group;

    // Crosshair sphere (inside group, so it inherits the rotation)
    const mkGeo = new THREE.SphereGeometry(3.2, 16, 16);
    const mkMat = new THREE.MeshBasicMaterial({
      color: Number.parseInt(CROSSHAIR_COLOR.slice(1), 16),
      depthTest: false,
    });
    const marker = new THREE.Mesh(mkGeo, mkMat);
    marker.renderOrder = 999;
    marker.visible = false;
    group.add(marker);
    markerRef.current = marker;

    if (!meshes || Object.keys(meshes).length === 0) {
      setLoading(false);
    } else {
      const loader = new GLTFLoader();
      const keys   = Object.keys(meshes).filter(k => meshes[k]);
      let pending  = keys.length;

      if (pending === 0) setLoading(false);

      keys.forEach((regionKey) => {
        const url = meshes[regionKey];
        const meta = MESH_METADATA[regionKey] || MESH_METADATA.brain;

        loader.load(
          url,
          (gltf) => {
            const model = gltf.scene;

            model.traverse((child) => {
              if (!child.isMesh) return;
              child.material = new THREE.MeshStandardMaterial({
                color:       meta.colorNum,
                opacity:     meta.defaultOpacity,
                transparent: meta.defaultTransparent,
                roughness:   meta.roughness,
                metalness:   meta.metalness,
                emissive:    meta.emissive ? new THREE.Color(meta.emissive) : new THREE.Color(0x000000),
                emissiveIntensity: meta.emissiveIntensity || 0,
                side:        meta.side,
                depthWrite:  meta.depthWrite,
              });
              child.renderOrder = meta.renderOrder;
              child.castShadow    = false;
              child.receiveShadow = false;
              child.userData.regionKey = regionKey;
            });

            group.add(model);
            modelsRef.current[regionKey] = model;

            // Center camera using world-space bounding box of brain (or cerebrum)
            if (regionKey === 'brain' || (!modelsRef.current['brain'] && regionKey === 'cerebrum')) {
              group.updateMatrixWorld(true);
              // new THREE.Box3().setFromObject(model) traverses children and computes the TRUE WORLD-SPACE bounding box!
              const worldBox = new THREE.Box3().setFromObject(model);
              const worldCenter = worldBox.getCenter(new THREE.Vector3());
              const worldSize   = worldBox.getSize(new THREE.Vector3());

              controls.target.copy(worldCenter);

              const maxDim = Math.max(worldSize.x, worldSize.y, worldSize.z) || 160;
              // Clinical Anterior-Superior perspective: camera positioned in front of patient (Anterior)
              // looking towards posterior (+Z), with top-of-head (+Y) pointing up.
              // Aligns 3D spatial orientation with 2D Coronal and Axial views:
              // - Patient Left is on observer's Right
              // - Patient Right is on observer's Left
              // - Anterior / Forehead faces forward towards clinician
              camera.position.set(
                worldCenter.x,
                worldCenter.y + maxDim * 0.45,
                worldCenter.z - maxDim * 1.65,
              );
              camera.lookAt(worldCenter);
              controls.update();
              controls.saveState();
            }

            pending--;
            if (pending <= 0) {
              setLoading(false);
              applySceneConfigRef.current?.();
            }
          },
          undefined,
          (err) => {
            console.warn(`[Viewer3D] GLB load warning [${regionKey}]:`, err);
            pending--;
            if (pending <= 0) {
              setLoading(false);
              applySceneConfigRef.current?.();
            }
          }
        );
      });
    }

    const grid = new THREE.GridHelper(400, 12, 0x1e293b, 0x111827);
    grid.position.y = -120;
    scene.add(grid);

    const animate = () => {
      animRef.current = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

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
      if (pointerRafRef.current) cancelAnimationFrame(pointerRafRef.current);
      renderer.dispose();
      modelsRef.current = {};
    };
  }, [meshes]);

  // ─── Crosshair Marker Position Sync ───────────────────────────────────────
  useEffect(() => {
    if (!markerRef.current || !crosshairMM) return;
    markerRef.current.position.set(crosshairMM[0], crosshairMM[1], crosshairMM[2]);
    markerRef.current.visible = true;
  }, [crosshairMM]);

  // ─── Auto-Rotate ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (controlsRef.current) controlsRef.current.autoRotate = autoRot;
  }, [autoRot]);

  const toggleVis = (key) => setVis(p => ({ ...p, [key]: !p[key] }));
  const resetCam  = () => controlsRef.current?.reset();

  // ─── Raycast Surface Picking (Optimized object reuse) ──────────────────────
  const pickMeshAt = useCallback((clientX, clientY) => {
    const container = wrapRef.current;
    if (!container || !cameraRef.current || !groupRef.current) return null;

    const rect = container.getBoundingClientRect();
    const mouse = mouseVecRef.current;
    mouse.set(
      ((clientX - rect.left) / rect.width) * 2 - 1,
      -((clientY - rect.top) / rect.height) * 2 + 1
    );

    const raycaster = raycasterRef.current;
    raycaster.setFromCamera(mouse, cameraRef.current);

    const targets = [];
    const models = modelsRef.current;
    if (models) {
      for (const key of Object.keys(models)) {
        const m = models[key];
        if (m && m.visible) {
          m.traverse((child) => {
            if (child.isMesh && child.visible && child !== markerRef.current) {
              targets.push(child);
            }
          });
        }
      }
    }

    if (targets.length === 0) return null;

    const intersects = raycaster.intersectObjects(targets, false);
    if (intersects.length === 0) return null;

    const hit = intersects[0];
    const hitKey = hit.object.userData.regionKey || 'brain';

    // Convert hit point to group local space (RAS+ world mm)
    const localPt = groupRef.current.worldToLocal(hit.point.clone());
    const mm = [
      Math.round(localPt.x * 10) / 10,
      Math.round(localPt.y * 10) / 10,
      Math.round(localPt.z * 10) / 10
    ];

    // Convert RAS+ mm to Voxel via inverse affine
    let vox = [0, 0, 0];
    if (invAffine) {
      vox = worldToVoxel(mm, invAffine);
    }

    const inBounds = isVoxelInBounds(vox, spatialMeta?.shape);
    if (!inBounds) return null;

    // Query voxel values via NiiVue volume inspector
    let voxelInfo = null;
    if (queryVoxel) {
      voxelInfo = queryVoxel(vox, mm);
    }

    let predVal = voxelInfo?.predVal || 0;
    // Direct physiological resolution from the picked 3D mesh surface
    if (predVal === 0) {
      if (hitKey === 'ed') predVal = 2;
      else if (hitKey === 'ncr') predVal = 1;
      else if (hitKey === 'et') predVal = 4;
    }

    const labelsObj = anatomyLookup?.labels || {};
    const anatVal = voxelInfo?.anatVal || 0;
    const labelMeta = labelsObj[String(anatVal)];
    const isUnavailable = anatomyLookup?.status === 'unavailable';

    // Derive deterministic geometric fallback if the extreme periphery has no atlas voxel
    const coarseHemi = Math.abs(mm[0]) < 2.0 ? 'Midline' : (mm[0] < 0 ? 'Left' : 'Right');
    let coarseLobe = 'Cerebral Cortex';
    if (mm[2] < -25 || hitKey === 'cerebellum') coarseLobe = 'Cerebellum';
    else if ((mm[2] < -10 && Math.abs(mm[0]) < 20 && mm[1] < 0) || hitKey === 'brainstem') coarseLobe = 'Brainstem';
    else if (mm[1] > 15) coarseLobe = 'Frontal Cortex';
    else if (mm[1] < -45) coarseLobe = 'Occipital Cortex';
    else if (mm[2] > 40) coarseLobe = 'Parietal Cortex';
    else coarseLobe = 'Temporal Cortex';

    const fallbackName = `${coarseLobe} (${coarseHemi} Hemisphere)`;
    const regionName = isUnavailable
      ? 'Anatomical labels unavailable'
      : (labelMeta?.name || (anatVal > 0 ? `Structure #${anatVal}` : fallbackName));

    return {
      mm,
      vox,
      predVal,
      anatVal,
      regionName,
      hemisphere: labelMeta?.hemisphere || coarseHemi,
      lobe: labelMeta?.lobe || coarseLobe,
      intensities: voxelInfo?.intensities || {},
      labelsUnavailable: isUnavailable,
      unavailableReason: anatomyLookup?.message || '',
      hitRegion: hitKey
    };
  }, [invAffine, spatialMeta?.shape, queryVoxel, anatomyLookup]);

  // ─── Pointer Event Handlers (RAF Throttled for 60fps responsiveness) ─────
  const handlePointerDown = (e) => {
    pointerDownPos.current = { x: e.clientX, y: e.clientY };
  };

  const handlePointerMove = (e) => {
    if (e.buttons !== 0) {
      if (pointerRafRef.current) {
        cancelAnimationFrame(pointerRafRef.current);
        pointerRafRef.current = null;
      }
      setHoverState(null);
      return;
    }

    lastPointerMoveRef.current = { clientX: e.clientX, clientY: e.clientY };

    if (!pointerRafRef.current) {
      pointerRafRef.current = requestAnimationFrame(() => {
        pointerRafRef.current = null;
        if (!lastPointerMoveRef.current) return;
        const { clientX, clientY } = lastPointerMoveRef.current;
        const picked = pickMeshAt(clientX, clientY);
        if (picked) {
          setHoverState({
            ...picked,
            x: clientX,
            y: clientY
          });
        } else {
          setHoverState((prev) => (prev ? null : prev));
        }
      });
    }
  };

  const handlePointerLeave = () => {
    if (pointerRafRef.current) {
      cancelAnimationFrame(pointerRafRef.current);
      pointerRafRef.current = null;
    }
    lastPointerMoveRef.current = null;
    setHoverState(null);
  };

  const handlePointerUp = (e) => {
    const dx = Math.abs(e.clientX - pointerDownPos.current.x);
    const dy = Math.abs(e.clientY - pointerDownPos.current.y);
    if (dx > 5 || dy > 5) return; // user was dragging/orbiting

    const picked = pickMeshAt(e.clientX, e.clientY);
    if (picked && onSelectLocation) {
      if (markerRef.current) {
        markerRef.current.position.set(picked.mm[0], picked.mm[1], picked.mm[2]);
        markerRef.current.visible = true;
      }
      onSelectLocation({
        ...picked,
        isPinned: true,
        source: '3d'
      });
    }
  };

  // Determine currently active visible toggles for the HUD bar
  const activeTumorKeys = useMemo(() => {
    if (tumorMode === 'cumulative') {
      return ['wt', 'tc', 'et'].filter(k => meshes && meshes[k]);
    }
    const keys = ['ed', 'ncr', 'et'].filter(k => meshes && meshes[k]);
    if (keys.length === 0) return ['wt', 'tc', 'et'].filter(k => meshes && meshes[k]);
    return keys;
  }, [tumorMode, meshes]);

  const activeBrainKeys = useMemo(() => {
    if (brainMode === 'divisions' && hasDivisions) {
      return ['cerebrum', 'cerebellum', 'brainstem'];
    }
    return ['brain'];
  }, [brainMode, hasDivisions]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, position: 'relative' }}>

      {/* ── Top Header Bar: Mode Selectors & Controls ───────────────────── */}
      <div style={{
        padding: '0.45rem 0.85rem',
        background: '#0f172a',
        borderBottom: '1px solid rgba(255,255,255,0.08)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        fontSize: '0.8rem', flexShrink: 0, flexWrap: 'wrap', gap: '0.5rem',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <span style={{ fontSize: '1.05rem' }}>🧠</span>
            <span style={{ fontWeight: 700, color: '#f8fafc', letterSpacing: '0.01em' }}>
              3D Workstation
            </span>
          </div>

          {/* Tumour Display Mode Selector */}
          {hasSeparateTumor && (
            <div style={{
              display: 'flex',
              background: 'rgba(255,255,255,0.06)',
              borderRadius: '6px',
              padding: '2px',
              border: '1px solid rgba(255,255,255,0.08)',
              gap: '2px',
            }}>
              <button
                onClick={() => setTumorMode('separate')}
                title="Render the 3 non-overlapping physiological parts (Edema, Necrosis, Active Rim)"
                style={{
                  border: 'none',
                  borderRadius: '4px',
                  padding: '3px 8px',
                  fontSize: '0.68rem',
                  fontWeight: tumorMode === 'separate' ? 700 : 500,
                  cursor: 'pointer',
                  background: tumorMode === 'separate' ? '#06b6d4' : 'transparent',
                  color: tumorMode === 'separate' ? '#0f172a' : '#94a3b8',
                  transition: 'all 0.15s ease',
                  display: 'flex', alignItems: 'center', gap: '3px',
                }}
              >
                <span>🧩</span> 3 Parts
              </button>

              <button
                onClick={() => setTumorMode('cutaway')}
                title="Render semi-transparent edema glass halo revealing solid core and active rim"
                style={{
                  border: 'none',
                  borderRadius: '4px',
                  padding: '3px 8px',
                  fontSize: '0.68rem',
                  fontWeight: tumorMode === 'cutaway' ? 700 : 500,
                  cursor: 'pointer',
                  background: tumorMode === 'cutaway' ? '#06b6d4' : 'transparent',
                  color: tumorMode === 'cutaway' ? '#0f172a' : '#94a3b8',
                  transition: 'all 0.15s ease',
                  display: 'flex', alignItems: 'center', gap: '3px',
                }}
              >
                <span>🩻</span> Glass Cutaway
              </button>

              <button
                onClick={() => setTumorMode('cumulative')}
                title="Classical BraTS cumulative evaluation envelopes (WT, TC, ET)"
                style={{
                  border: 'none',
                  borderRadius: '4px',
                  padding: '3px 8px',
                  fontSize: '0.68rem',
                  fontWeight: tumorMode === 'cumulative' ? 700 : 500,
                  cursor: 'pointer',
                  background: tumorMode === 'cumulative' ? '#06b6d4' : 'transparent',
                  color: tumorMode === 'cumulative' ? '#0f172a' : '#94a3b8',
                  transition: 'all 0.15s ease',
                  display: 'flex', alignItems: 'center', gap: '3px',
                }}
              >
                <span>🔬</span> Cumulative
              </button>
            </div>
          )}

          {/* Brain Mode Selector (Cortex vs 3 Divisions) */}
          {hasDivisions && (
            <div style={{
              display: 'flex',
              background: 'rgba(255,255,255,0.06)',
              borderRadius: '6px',
              padding: '2px',
              border: '1px solid rgba(255,255,255,0.08)',
              gap: '2px',
            }}>
              <button
                onClick={() => setBrainMode('cortex')}
                title="Single high-fidelity cortical surface silhouette"
                style={{
                  border: 'none',
                  borderRadius: '4px',
                  padding: '3px 7px',
                  fontSize: '0.68rem',
                  fontWeight: brainMode === 'cortex' ? 700 : 500,
                  cursor: 'pointer',
                  background: brainMode === 'cortex' ? 'rgba(255,255,255,0.18)' : 'transparent',
                  color: brainMode === 'cortex' ? '#f8fafc' : '#94a3b8',
                  transition: 'all 0.15s ease',
                }}
              >
                Cortex
              </button>
              <button
                onClick={() => setBrainMode('divisions')}
                title="3 Anatomical Brain Divisions: Cerebrum, Cerebellum, Brainstem"
                style={{
                  border: 'none',
                  borderRadius: '4px',
                  padding: '3px 7px',
                  fontSize: '0.68rem',
                  fontWeight: brainMode === 'divisions' ? 700 : 500,
                  cursor: 'pointer',
                  background: brainMode === 'divisions' ? '#8b5cf6' : 'transparent',
                  color: brainMode === 'divisions' ? '#ffffff' : '#94a3b8',
                  transition: 'all 0.15s ease',
                }}
              >
                3 Divisions
              </button>
            </div>
          )}
        </div>

        {/* Camera and Quick Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <button
            onClick={() => setAutoRot(p => !p)}
            style={{
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: '5px',
              padding: '2px 8px',
              fontSize: '0.68rem',
              cursor: 'pointer',
              background: autoRot ? 'rgba(6,182,212,0.2)' : 'rgba(255,255,255,0.04)',
              color: autoRot ? '#38bdf8' : '#94a3b8',
              fontWeight: autoRot ? 700 : 400,
              display: 'flex', alignItems: 'center', gap: '3px',
              transition: 'all 0.15s ease',
            }}
          >
            ↻ Auto
          </button>

          <button
            onClick={resetCam}
            title="Reset 3D camera to default neurological angle"
            style={{
              display: 'flex', alignItems: 'center', gap: '3px',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: '5px',
              padding: '2px 8px',
              fontSize: '0.68rem',
              cursor: 'pointer',
              background: 'rgba(255,255,255,0.04)',
              color: '#94a3b8',
              transition: 'all 0.15s ease',
            }}
          >
            <RotateCcw size={10} /> Reset
          </button>
        </div>
      </div>

      {/* ── Sub-Toolbar: Active Mesh Visibility Pills ──────────────────── */}
      <div style={{
        padding: '0.35rem 0.85rem',
        background: '#090e1a',
        borderBottom: '1px solid rgba(255,255,255,0.05)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        fontSize: '0.72rem', flexShrink: 0, flexWrap: 'wrap', gap: '0.4rem',
      }}>
        {/* Brain visibility toggles */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.64rem', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em', marginRight: '2px' }}>
            Brain:
          </span>
          {activeBrainKeys.map((key) => {
            const meta = MESH_METADATA[key] || MESH_METADATA.brain;
            const isVisible = vis[key];
            return (
              <button
                key={key}
                onClick={() => toggleVis(key)}
                style={{
                  display: 'flex', alignItems: 'center', gap: '4px',
                  border: isVisible ? `1px solid ${meta.colorHex}55` : '1px solid rgba(255,255,255,0.08)',
                  background: isVisible ? `${meta.colorHex}18` : 'rgba(255,255,255,0.02)',
                  cursor: 'pointer',
                  fontSize: '0.68rem',
                  padding: '2px 7px',
                  borderRadius: '4px',
                  color: isVisible ? '#f8fafc' : '#64748b',
                  transition: 'all 0.15s ease',
                }}
              >
                <span style={{
                  width: 7, height: 7, borderRadius: '50%',
                  background: meta.colorHex,
                  boxShadow: isVisible ? `0 0 6px ${meta.colorHex}` : 'none',
                }} />
                <span>{meta.label}</span>
              </button>
            );
          })}
        </div>

        {/* Tumour visibility toggles */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.64rem', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em', marginRight: '2px' }}>
            Tumour:
          </span>
          {activeTumorKeys.map((key) => {
            const meta = MESH_METADATA[key];
            const isVisible = vis[key];
            return (
              <button
                key={key}
                onClick={() => toggleVis(key)}
                title={meta.long}
                style={{
                  display: 'flex', alignItems: 'center', gap: '4px',
                  border: isVisible ? `1px solid ${meta.colorHex}66` : '1px solid rgba(255,255,255,0.08)',
                  background: isVisible ? `${meta.colorHex}22` : 'rgba(255,255,255,0.02)',
                  cursor: 'pointer',
                  fontSize: '0.68rem',
                  padding: '2px 7px',
                  borderRadius: '4px',
                  color: isVisible ? '#f8fafc' : '#64748b',
                  transition: 'all 0.15s ease',
                }}
              >
                <span style={{
                  width: 7, height: 7, borderRadius: '50%',
                  background: meta.colorHex,
                  boxShadow: isVisible ? `0 0 8px ${meta.colorHex}` : 'none',
                }} />
                <span style={{ fontWeight: isVisible ? 600 : 400 }}>{meta.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Three.js Canvas Container ────────────────────────────────────── */}
      <div
        ref={wrapRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerLeave={handlePointerLeave}
        onPointerUp={handlePointerUp}
        style={{ flex: 1, position: 'relative', background: '#0b1120', overflow: 'hidden', minHeight: 0, cursor: 'grab' }}
      >
        {/* Loading overlay */}
        {loading && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 5,
            background: 'rgba(11,17,32,0.88)',
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: '0.75rem',
            pointerEvents: 'none',
          }}>
            <div style={{
              width: 38, height: 38,
              border: '3px solid rgba(255,255,255,0.1)',
              borderTop: '3px solid #06b6d4',
              borderRadius: '50%',
              animation: '3dSpin 0.8s linear infinite',
            }} />
            <span style={{ fontSize: '0.8rem', color: '#94a3b8', letterSpacing: '0.02em' }}>
              Synthesizing 3D Anatomical Meshes…
            </span>
            <style>{`@keyframes 3dSpin { to { transform:rotate(360deg); } }`}</style>
          </div>
        )}

        {/* Visual Badge Overlay */}
        <div style={{
          position: 'absolute', top: 12, left: 12, zIndex: 2,
          pointerEvents: 'none',
          display: 'flex', flexDirection: 'column', gap: '4px'
        }}>
          <span style={{
            fontSize: '0.62rem',
            background: 'rgba(15,23,42,0.75)',
            border: '1px solid rgba(255,255,255,0.1)',
            padding: '2px 6px',
            borderRadius: '4px',
            color: '#38bdf8',
            fontFamily: 'var(--font-mono)',
          }}>
            RAS+ Space · Raycast Voxel Picking
          </span>
          {tumorMode === 'separate' && (
            <span style={{
              fontSize: '0.60rem',
              background: 'rgba(6,182,212,0.15)',
              border: '1px solid rgba(6,182,212,0.3)',
              padding: '2px 6px',
              borderRadius: '4px',
              color: '#67e8f9',
              display: 'flex', alignItems: 'center', gap: '3px'
            }}>
              <Sparkles size={9} /> 3 Non-Overlapping Compartments
            </span>
          )}
          {tumorMode === 'cutaway' && (
            <span style={{
              fontSize: '0.60rem',
              background: 'rgba(245,158,11,0.15)',
              border: '1px solid rgba(245,158,11,0.3)',
              padding: '2px 6px',
              borderRadius: '4px',
              color: '#fcd34d',
            }}>
              🩻 Translucent Edema Glass Halo
            </span>
          )}
        </div>
      </div>

      {/* ── Floating Hover Tooltip ───────────────────────────────────────── */}
      {hoverState && (
        <HoverTooltip
          x={hoverState.x}
          y={hoverState.y}
          mm={hoverState.mm}
          vox={hoverState.vox}
          predVal={hoverState.predVal}
          anatVal={hoverState.anatVal}
          regionName={hoverState.regionName}
          hemisphere={hoverState.hemisphere}
          lobe={hoverState.lobe}
          activeIntensity={hoverState.intensities?.t1}
          activeModality="T1"
          labelsUnavailable={hoverState.labelsUnavailable}
          unavailableReason={hoverState.unavailableReason}
        />
      )}

      {/* ── HUD Footer: Brain Opacity Slider + Legend + Hints ───────────── */}
      <div style={{
        padding: '0.4rem 0.85rem',
        background: '#090e1a',
        borderTop: '1px solid rgba(255,255,255,0.06)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexShrink: 0, flexWrap: 'wrap', gap: '0.5rem',
      }}>
        {/* Brain opacity control */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', color: '#94a3b8', fontSize: '0.7rem' }}>
          <span>Brain Glass:</span>
          <input
            type="range"
            min="0"
            max="0.50"
            step="0.02"
            value={brainAlpha}
            onChange={e => setBrainAlpha(parseFloat(e.target.value))}
            style={{ width: '70px', cursor: 'pointer', accentColor: '#06b6d4' }}
          />
          <span style={{ fontFamily: 'var(--font-mono)', color: '#38bdf8', minWidth: '2.5em', fontWeight: 600 }}>
            {Math.round(brainAlpha * 100)}%
          </span>
        </div>

        {/* Legend dots */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem', flexWrap: 'wrap' }}>
          {activeTumorKeys.map((key) => {
            const meta = MESH_METADATA[key];
            return (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.67rem', color: '#94a3b8' }}>
                <span style={{ width: 8, height: 8, borderRadius: '2px', background: meta.colorHex, display: 'inline-block' }} />
                <span>{meta.badge ? `${meta.label} (${meta.badge})` : meta.label}</span>
              </div>
            );
          })}
        </div>

        {/* Inspection Hint */}
        <span style={{ fontSize: '0.62rem', color: '#475569' }}>
          Hover 3D surface to inspect · Click to pin · Drag to rotate
        </span>
      </div>
    </div>
  );
}

"""HTML fragments for embedded WebGL previews (Three.js).

Used inside ``streamlit.components.html``. Prefer passing a **local**
``three_script_src`` (e.g. Streamlit ``app/static/vendor/three.min.js``) so the
launcher works offline; CDN remains the fallback when the file is missing.
"""

from __future__ import annotations

import html
import json
from typing import Any, Dict

DEFAULT_THREE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"


def build_threejs_block_preview_html(
    *,
    dom_id: str,
    png_base64: str,
    height: int = 420,
    three_script_src: str = DEFAULT_THREE_CDN,
    preview_mode: str = "texture_cube",
) -> str:
    """
    ``png_base64`` is raw base64 only (no ``data:`` prefix).

    ``preview_mode``: ``texture_cube`` (same texture on all faces of a unit cube)
    or ``item_plane`` (single textured quad, closer to ``item/generated``).
    """
    safe_id = html.escape(dom_id, quote=True)
    safe_three = html.escape(three_script_src or DEFAULT_THREE_CDN, quote=True)
    blob = "".join(str(png_base64 or "").split())
    height_i = max(220, min(int(height or 420), 900))
    mode_js = "item_plane" if str(preview_mode or "").lower() == "item_plane" else "texture_cube"
    return f"""<div style="width:100%;max-width:100%;">
<div id="host-{safe_id}" style="width:100%;height:{height_i}px;border-radius:14px;border:1px solid rgba(148,163,184,0.28);
overflow:hidden;background:radial-gradient(120% 80% at 30% 0%, rgba(30,41,59,0.95), rgba(2,6,23,0.98));position:relative;"></div>
<script type="text/plain" id="b64-{safe_id}">{blob}</script>
<script type="text/plain" id="mode-{safe_id}">{mode_js}</script>
<script src="{safe_three}" crossorigin="anonymous"></script>
<script>
(function() {{
  var HID = "{safe_id}";
  function run() {{
    var host = document.getElementById("host-" + HID);
    if (!host) return;
    if (typeof THREE === "undefined") {{
      host.innerHTML = '<div style="padding:14px;color:#94a3b8;font:600 13px system-ui,sans-serif;">WebGL preview could not load Three.js (missing vendor script or blocked network).</div>';
      return;
    }}
    var b64el = document.getElementById("b64-" + HID);
    var b64 = (b64el && b64el.textContent) ? b64el.textContent.trim() : "";
    if (!b64) {{
      host.innerHTML = '<div style="padding:14px;color:#94a3b8;font:600 13px system-ui,sans-serif;">No texture bytes for preview.</div>';
      return;
    }}
    var modeEl = document.getElementById("mode-" + HID);
    var mode = (modeEl && modeEl.textContent) ? modeEl.textContent.trim() : "texture_cube";
    var dataUrl = "data:image/png;base64," + b64;
    var W = Math.max(120, host.clientWidth || 600);
    var H = {height_i};
    var scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0f172a);
    scene.fog = new THREE.Fog(0x0f172a, 2.8, 14);
    var camera = new THREE.PerspectiveCamera(40, W / H, 0.08, 60);
    camera.position.set(1.95, 1.42, 2.45);
    if (mode === "item_plane") {{
      camera.position.set(0, 0.15, 1.35);
    }}
    var renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: false, powerPreference: "high-performance" }});
    var pr = Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(pr);
    renderer.setSize(W, H);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    if (renderer.outputEncoding !== undefined) renderer.outputEncoding = THREE.sRGBEncoding;
    if (renderer.toneMapping !== undefined) renderer.toneMapping = THREE.ACESFilmicToneMapping;
    if (renderer.toneMappingExposure !== undefined) renderer.toneMappingExposure = 1.05;
    host.appendChild(renderer.domElement);
    scene.add(new THREE.AmbientLight(0x7c8aa8, 0.32));
    var hemi = new THREE.HemisphereLight(0xb6c6ff, 0x0b1220, 0.78);
    scene.add(hemi);
    var dir = new THREE.DirectionalLight(0xffffff, 0.92);
    dir.position.set(2.6, 4.4, 2.9);
    dir.castShadow = true;
    dir.shadow.mapSize.width = 1024;
    dir.shadow.mapSize.height = 1024;
    scene.add(dir);
    var rim = new THREE.DirectionalLight(0x38bdf8, 0.35);
    rim.position.set(-3.2, 1.5, -2.4);
    scene.add(rim);
    var geom = (mode === "item_plane")
      ? new THREE.PlaneGeometry(1, 1)
      : new THREE.BoxGeometry(1, 1, 1);
    var mat = new THREE.MeshStandardMaterial({{ color: 0xffffff, metalness: 0.14, roughness: 0.58, side: THREE.DoubleSide }});
    var mesh = new THREE.Mesh(geom, mat);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    if (mode === "item_plane") {{
      mesh.rotation.x = -Math.PI / 2;
      mesh.position.y = 0.05;
    }}
    scene.add(mesh);
    var ground = new THREE.Mesh(
      new THREE.PlaneGeometry(9, 9),
      new THREE.MeshStandardMaterial({{ color: 0x111b2e, metalness: 0.06, roughness: 0.94 }})
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.72;
    ground.receiveShadow = true;
    scene.add(ground);
    new THREE.TextureLoader().load(
      dataUrl,
      function (tex) {{
        tex.magFilter = THREE.NearestFilter;
        tex.minFilter = THREE.LinearMipmapLinearFilter;
        tex.generateMipmaps = true;
        if (tex.encoding !== undefined) tex.encoding = THREE.sRGBEncoding;
        mat.map = tex;
        mat.needsUpdate = true;
      }},
      undefined,
      function () {{
        mat.color = new THREE.Color(0x64748b);
        mat.needsUpdate = true;
      }}
    );
    var dragging = false, lx = 0, ly = 0;
    renderer.domElement.addEventListener("pointerdown", function (e) {{
      dragging = true;
      lx = e.clientX;
      ly = e.clientY;
      renderer.domElement.style.cursor = "grabbing";
    }});
    function stop() {{
      dragging = false;
      renderer.domElement.style.cursor = "grab";
    }}
    renderer.domElement.addEventListener("pointerup", stop);
    renderer.domElement.addEventListener("pointerleave", stop);
    renderer.domElement.addEventListener("pointermove", function (e) {{
      if (!dragging) return;
      var dx = e.clientX - lx, dy = e.clientY - ly;
      lx = e.clientX;
      ly = e.clientY;
      mesh.rotation.y += dx * 0.0065;
      if (mode !== "item_plane") {{
        mesh.rotation.x += dy * 0.0065;
        mesh.rotation.x = Math.max(-0.95, Math.min(0.95, mesh.rotation.x));
      }}
    }});
    renderer.domElement.style.cursor = "grab";
    if (typeof ResizeObserver !== "undefined") {{
      var ro = new ResizeObserver(function () {{
        var w2 = Math.max(120, host.clientWidth || W);
        camera.aspect = w2 / H;
        camera.updateProjectionMatrix();
        renderer.setSize(w2, H);
      }});
      ro.observe(host);
    }}
    function tick() {{
      requestAnimationFrame(tick);
      mesh.rotation.y += 0.00135;
      renderer.render(scene, camera);
    }}
    tick();
  }}
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run);
  else run();
}})();
</script>
</div>"""


def build_threejs_uv_mesh_preview_html(
    *,
    dom_id: str,
    mesh: Dict[str, Any],
    png_base64: str,
    height: int = 420,
    three_script_src: str = DEFAULT_THREE_CDN,
) -> str:
    """``mesh`` from :func:`forager_ai.ui.mc_model_mesh.mesh_from_java_model` (positions, uvs, indices)."""
    safe_id = html.escape(dom_id, quote=True)
    safe_three = html.escape(three_script_src or DEFAULT_THREE_CDN, quote=True)
    blob = "".join(str(png_base64 or "").split())
    mesh_json = json.dumps(mesh, separators=(",", ":"))
    mesh_esc = html.escape(mesh_json, quote=False)
    height_i = max(220, min(int(height or 420), 900))
    return f"""<div style="width:100%;max-width:100%;">
<div id="hostm-{safe_id}" style="width:100%;height:{height_i}px;border-radius:14px;border:1px solid rgba(148,163,184,0.28);
overflow:hidden;background:radial-gradient(120% 80% at 30% 0%, rgba(30,41,59,0.95), rgba(2,6,23,0.98));position:relative;"></div>
<script type="application/json" id="mesh-{safe_id}">{mesh_esc}</script>
<script type="text/plain" id="b64m-{safe_id}">{blob}</script>
<script src="{safe_three}" crossorigin="anonymous"></script>
<script>
(function() {{
  var HID = "{safe_id}";
  function run() {{
    var host = document.getElementById("hostm-" + HID);
    if (!host) return;
    if (typeof THREE === "undefined") {{
      host.innerHTML = '<div style="padding:14px;color:#94a3b8;font:600 13px system-ui,sans-serif;">WebGL preview could not load Three.js.</div>';
      return;
    }}
    var mdoc = document.getElementById("mesh-" + HID);
    var mp = JSON.parse(mdoc.textContent);
    var b64el = document.getElementById("b64m-" + HID);
    var b64 = (b64el && b64el.textContent) ? b64el.textContent.trim() : "";
    if (!b64 || !mp || !mp.positions || !mp.uvs || !mp.indices) {{
      host.innerHTML = '<div style="padding:14px;color:#94a3b8;font:600 13px system-ui,sans-serif;">Invalid mesh or texture payload.</div>';
      return;
    }}
    var dataUrl = "data:image/png;base64," + b64;
    var W = Math.max(120, host.clientWidth || 600);
    var H = {height_i};
    var scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0f172a);
    scene.fog = new THREE.Fog(0x0f172a, 2.8, 16);
    var camera = new THREE.PerspectiveCamera(40, W / H, 0.08, 60);
    camera.position.set(2.1, 1.55, 2.35);
    var renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: false, powerPreference: "high-performance" }});
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(W, H);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    if (renderer.outputEncoding !== undefined) renderer.outputEncoding = THREE.sRGBEncoding;
    if (renderer.toneMapping !== undefined) renderer.toneMapping = THREE.ACESFilmicToneMapping;
    if (renderer.toneMappingExposure !== undefined) renderer.toneMappingExposure = 1.05;
    host.appendChild(renderer.domElement);
    scene.add(new THREE.AmbientLight(0x7c8aa8, 0.3));
    scene.add(new THREE.HemisphereLight(0xb6c6ff, 0x0b1220, 0.75));
    var dir = new THREE.DirectionalLight(0xffffff, 0.9);
    dir.position.set(2.8, 4.2, 2.6);
    dir.castShadow = true;
    scene.add(dir);
    var geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.Float32BufferAttribute(new Float32Array(mp.positions), 3));
    geom.setAttribute("uv", new THREE.Float32BufferAttribute(new Float32Array(mp.uvs), 2));
    geom.setIndex(mp.indices);
    geom.computeVertexNormals();
    var mat = new THREE.MeshStandardMaterial({{ color: 0xffffff, metalness: 0.12, roughness: 0.55 }});
    var meshObj = new THREE.Mesh(geom, mat);
    meshObj.castShadow = true;
    meshObj.receiveShadow = true;
    scene.add(meshObj);
    var ground = new THREE.Mesh(
      new THREE.PlaneGeometry(10, 10),
      new THREE.MeshStandardMaterial({{ color: 0x111b2e, metalness: 0.06, roughness: 0.94 }})
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.78;
    ground.receiveShadow = true;
    scene.add(ground);
    new THREE.TextureLoader().load(
      dataUrl,
      function (tex) {{
        tex.magFilter = THREE.NearestFilter;
        tex.minFilter = THREE.LinearMipmapLinearFilter;
        tex.generateMipmaps = true;
        if (tex.encoding !== undefined) tex.encoding = THREE.sRGBEncoding;
        mat.map = tex;
        mat.needsUpdate = true;
      }},
      undefined,
      function () {{
        mat.color = new THREE.Color(0x64748b);
        mat.needsUpdate = true;
      }}
    );
    var dragging = false, lx = 0, ly = 0;
    renderer.domElement.addEventListener("pointerdown", function (e) {{
      dragging = true;
      lx = e.clientX;
      ly = e.clientY;
      renderer.domElement.style.cursor = "grabbing";
    }});
    function stop() {{ dragging = false; renderer.domElement.style.cursor = "grab"; }}
    renderer.domElement.addEventListener("pointerup", stop);
    renderer.domElement.addEventListener("pointerleave", stop);
    renderer.domElement.addEventListener("pointermove", function (e) {{
      if (!dragging) return;
      var dx = e.clientX - lx, dy = e.clientY - ly;
      lx = e.clientX;
      ly = e.clientY;
      meshObj.rotation.y += dx * 0.0065;
      meshObj.rotation.x += dy * 0.0045;
      meshObj.rotation.x = Math.max(-0.85, Math.min(0.85, meshObj.rotation.x));
    }});
    renderer.domElement.style.cursor = "grab";
    if (typeof ResizeObserver !== "undefined") {{
      var ro = new ResizeObserver(function () {{
        var w2 = Math.max(120, host.clientWidth || W);
        camera.aspect = w2 / H;
        camera.updateProjectionMatrix();
        renderer.setSize(w2, H);
      }});
      ro.observe(host);
    }}
    function tick() {{
      requestAnimationFrame(tick);
      meshObj.rotation.y += 0.0011;
      renderer.render(scene, camera);
    }}
    tick();
  }}
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run);
  else run();
}})();
</script>
</div>"""

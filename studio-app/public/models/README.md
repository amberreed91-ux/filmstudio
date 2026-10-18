# Studio Lobby 3D Models

Place custom Blender exports here to replace the procedural 3D lobby stage.

- Supported formats: `.glb` (preferred) and `.gltf`
- Main file: `studio_lobby.glb` — loaded automatically by
  `studio-app/src/components/Interactive3DLobby.tsx` when present.
- When `studio_lobby.glb` exists, it renders with HDRI environment
  lighting (`<Environment preset="city" />` from `@react-three/drei`).
- When absent (or unloadable), the lobby gracefully falls back to the
  enhanced procedural scene (stage disc, accent ring, hotspots, grid).

Export tips (Blender → glTF):
- File → Export → glTF 2.0 (`.glb`), +Y up, apply transforms.
- Bake / embed textures so the single `.glb` is self-contained.
- Keep the model near origin, roughly within a ±6m radius, floor at y=0.

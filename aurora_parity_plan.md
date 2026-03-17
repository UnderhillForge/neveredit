# Aurora Toolset Parity Plan

## Goal
Reach practical parity with the original Aurora Toolset editing workflow for module/area authoring while preserving neveredit's current architecture.

## Status Legend
- Exists: implemented and usable now.
- Partial: present but incomplete compared to Aurora expectations.
- Missing: not implemented in current UX/workflow.

## Parity Matrix

| Feature Area | Status | Evidence | Gap To Close |
|---|---|---|---|
| File open/save/module resource merge | Exists | neveredit/ui/NeverEditMainApp.py (File menu, open/save/add ERF/add resource) | None for baseline parity. |
| Module tree root sections | Exists | Areas, Scripts, Conversations, Factions, Sounds, Triggers, Encounters roots added; BP objects attached as tree data giving Properties tab access | None for baseline parity. |
| Area subtree object categories | Exists | neveredit/ui/NeverEditMainApp.py subtreeFromArea now adds Doors/Placeables/Creatures/Items/WayPoints/Sounds/Triggers/Encounters | None for baseline parity. |
| Area content data model | Exists | neveredit/game/Area.py now parses/adds Trigger and Encounter lists alongside sounds | None for baseline parity. |
| Generic property editing | Exists | neveredit/ui/PropWindow.py dynamic controls for many NWN property types | Improve specialized UX for high-frequency Aurora properties. |
| Module/Area property workflows | Exists | PropertiesDialogs.py — tabbed Area Properties (General/Lighting/Sound/Scripts) and Module Properties (General/Events/HAKs) dialogs; wired to File/Edit menus and tree right-click | None for baseline parity. |
| Script editor integration | Partial | Window menu + ScriptEditor frame in NeverEditMainApp | Build/compile pipeline still depends on external compiler availability. |
| Toolbar mode: Select/Move | Exists | neveredit/ui/ToolPalette.py + MapWindow selection logic | None for baseline. |
| Toolbar mode: Rotate | Exists | ToolPalette + MapWindow rotation handling | None for baseline. |
| Toolbar mode: Paint/place instance | Partial | ToolPalette paint + map placement from active palette | Coverage limited by palette type exclusions and blueprint support. |
| Ambient sound placement/editing | Partial | ToolPalette ambient tool + MapWindow radius editing and preview | Good feature, but needs tighter parity UX and listing integration. |
| 2D terrain drafting tool | Partial | MapWindow MAP2D_DRAW_TOOL, brush controls, import/export | Not Aurora tile painting; currently planning overlay, not true tile/terrain authoring. |
| Palette tabs available to users | Exists | All PALETTE_TYPES now loaded in ToolPalette; Sound and Store tabs appear when their .itp palette files are available; missing palettes degrade gracefully with a log warning | None for baseline parity. |
| Palette blueprint support by type | Exists | SoundBP (Sound.py) and StoreBP (Store.py) implemented; Palette.py wired; ToolPalette loads all types with graceful fallback | None for baseline parity. |
| Camera: orbit/pan/zoom | Exists | MapWindow right-drag orbit, middle/shift-right pan, wheel zoom | None for baseline parity. |
| Object transform shortcuts | Exists | Arrow keys nudge XY, PgUp/PgDn nudge Z, [/] rotate ±15°; Ctrl+drag vertical move; status-bar hint shown on selection | None for baseline parity. |
| Layer visibility controls | Exists | MapLayersWindow + MapWindow layer toggles + persistence + selection gating in MapWindow | None for baseline; can be refined later. |
| Keyboard shortcut discoverability | Partial | Tool-specific overlays in MapWindow | Add central shortcut reference and menu entries. |
| Build/Test module action | Extra Feature | Tools menu stubs exist; real compile/launch pipeline deferred | See Extra Features section. |
| Wizard workflows (encounter/item/placeable/etc.) | Missing | No wizard windows mirroring Aurora workflows | Add staged wizard dialogs for common authoring tasks. |

## Recommended Phases

### Phase 0: Parity Spine (high impact, low risk)
1. Expand area tree coverage to include Sounds first, then Trigger/Encounter placeholders.
2. Re-enable hidden palette tabs where support exists (Item at minimum).
3. Add explicit "Mode" and "View" menu entries that mirror current map controls.
4. Add a central shortcut/help panel so power features are discoverable.

Target files:
- neveredit/ui/NeverEditMainApp.py
- neveredit/ui/ToolPalette.py
- neveredit/ui/MapWindow.py
- neveredit/game/Area.py

### Phase 1: Core Object Parity
1. Implement Trigger and Encounter runtime data wrappers and area list integration.
2. Implement missing palette blueprint support (Trigger/Encounter/Sound/Store).
3. Extend map placement logic for new instance types.
4. Add tree synchronization and selection mapping for new object kinds.

Target files:
- neveredit/game/Area.py
- neveredit/game/Palette.py
- neveredit/game (EncounterBP/SoundBP/StoreBP classes as needed; TriggerBP already exists)
- neveredit/ui/MapWindow.py
- neveredit/ui/NeverEditMainApp.py

### Phase 2: Authoring Workflow Parity
1. Add dedicated module/area property command surfaces and curated dialogs.
2. Add first-pass wizards (encounter and placeable) with sensible defaults.

Target files:
- neveredit/ui/NeverEditMainApp.py
- neveredit/ui/PreferencesDialog.py (if compiler/config wiring needed)
- neveredit/ui (new wizard windows)
- neveredit/game/Script.py and compile integration points

### Phase 3: UX Polish and Throughput
1. Batch editing and multi-select operations.
2. Better undo/redo around map operations.
3. Performance and redraw tuning for large modules.

## Immediate Implementation Backlog (execution order)
1. [DONE 2026-03-15] Add Sounds node to area subtree and tree-selection mapping.
2. [DONE 2026-03-15] Remove Item from ToolPalette exclusion list and validate painting flow.
3. [DONE 2026-03-15] Add lightweight Tools menu with "Build Module" and "Test Module" placeholders.
4. [DONE 2026-03-16] Add Trigger/Encounter entries as visible disabled placeholders in palette/tree to make gaps explicit.
5. [DONE 2026-03-16] Implement Trigger and Encounter blueprints/data/tree/map integration end-to-end.
6. [DONE 2026-03-16] Add curated Area Properties and Module Properties tabbed dialogs (File/Edit menus + tree right-click).
7. [DONE 2026-03-16] Extend glTF exporter — textures (PNG), PBR materials, animation tracks; folder export with DirDialog prompt.
8. [DONE 2026-03-16] MapWindow right-click context menu (Edit/Copy/Paste/Save Blueprint/Remove/Export for Web).

## Definition of Done for "Aurora-like daily use"
- A builder can open a module, navigate all key object classes from tree and palette, place/edit them on map, and save without CLI steps.
- Camera/mode/shortcut behavior is discoverable in-UI.
- Module and area properties are reachable through explicit commands, not only inferred selection flow.

## Extra Features
These go beyond Aurora parity and depend on external tooling or significant new infrastructure. Implement only after core parity is achieved.

- **Build/Test module**: Wire Build Module/Test Module menu stubs to a real NWScript compile pipeline (nwnnsscomp or nwnsc) and NWN process launcher. Requires compiler binary configuration in Preferences, stdout/stderr capture into a results dialog, and error-line linking back to the script editor.

## Original List
The Neverwinter Nights (NWN) Aurora Toolset is a complex, feature-rich application. Its interface is categorized into main menus, toolbars, palettes, and area viewers, with hundreds of functions for creating modules. 
Here is a breakdown of the major buttons, tools, and UI elements, primarily based on the standard 1.69 and Enhanced Edition toolsets: 

1. Main Toolbar Buttons (Top)
New: Create a new module.
Open: Open an existing module.
Save: Save the current module.
Build/Test Module (F9): Compile scripts and run the module in-game to test.
Module Properties: Set name, description, and rules for the entire module.
Area Wizard: [DONE 2026-03-16] Create a new area (interior or exterior).
Area Properties: Adjust lighting, skybox, ambient music, and fog.
Script Editor: Open the script editor to write custom NWScript code.
Conversation Editor: Create dialogues for NPCs.
Encounter Editor: Design random enemy encounters.
Faction Editor: Modify relationships between different groups.
Item/Creature/Placeable/Door Wizard: Create new items/entities from templates. 

2. View/Mode Controls
Select Objects (F2): Select and move objects/tiles.
Paint Objects (F3): Place objects from the palette into the area.
Select Terrain (F4): Select specific terrain tiles.
Paint Terrain (F5): Paint terrain tiles (e.g., grass, floor, water).
Toggle Grid: Display/hide the grid overlay on the terrain.
Toggle Lighting/Day/Night: Toggle area lighting to check how it looks at different times.
Toggle Shadows: Enable/disable shadows to improve performance or view quality.
Toggle Fog: Toggle visibility of atmospheric fog. 

3. Palette Buttons (Right Side)
Placeable Objects: Cages, furniture, debris, etc..
Creatures: NPCs, monsters, allies.
Items: Weapons, armor, quest items.
Doors: Doors for interiors and exteriors.
Triggers: Invisible zones that start conversations or cutscenes.
Sound: Ambient sounds (birds, wind, water).
Waypoints: Invisible markers for scripting and AI movement.
Doors/Areas/Doors/etc.: Specific tabs for sub-types of objects.
Start Location: Sets the location where players first appear. 

4. Area Viewer Camera Controls (Bottom)
Pan: Move the camera horizontally/vertically (Ctrl+Left Drag).
Rotate: Rotate the view (Ctrl+Right Drag or Mouse Wheel).
Zoom: Zoom in/out (Mouse Wheel).
Raise/Lower View: Changes camera height.
Drop to Ground: Press Space to drop a selected object to the terrain surface. 

5. Brush Controls (Top/Specific Modes) 
Brush Size: Adjust the radius of the terrain or object painter ([ or ]).
Pressure: Adjust the intensity of the brush (- or =). 

6. Module Contents (Left Panel) 
Tree Structure: Contains lists of Areas, Conversations, Scripts, and Doors.
Collapse/Expand: Plus and minus symbols to manage list visibility. 

7. Other Essential Shortcuts
Ctrl+C/V/Z: Standard Windows Copy, Paste, Undo.
Shift + Right Click Drag: Rotate an object.
ALT + Move Mouse: Raise/lower objects. 
Note: The Aurora Toolset frequently requires toggling on "View" -> "Custom" for the full list of custom items, creatures, and objects created within the module. 
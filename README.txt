FNV Asset Sorter 1.0

Portable Windows 10/11 x64 program. Extract the complete release ZIP, retain
app/ and runtime/, and run FNV Asset Sorter.exe. Python/Tk are bundled.
No administrator access, network connection, or separately installed Python.

Choose an ESP/ESM, an input folder with Meshes/Textures/Sound/etc., a new or
empty output folder, and the game installation or Data folder. Preview writes
nothing. Sort copies matching files to output/required/ preserving paths.
Optionally copy the rest to output/not required/. Reports identify every input
file and unresolved reference. Plugins and source files are never edited.
Vanilla exclusion is on by default and requires official texture BSAs. Only
byte-identical textures are omitted; modified vanilla replacements are kept.

Master scanning searches beside the selected plugin and in Game/Data. It scans
whole masters conservatively, rather than resolving winning records/FormIDs.
Thus it may retain extra assets. Missing masters appear in Activity/reports.
NIF dependencies, likely shader companions, and matching LIP files are followed.
Conservative mode retains character/animation/generated and non-mesh/texture
assets. Turn it off only if you will review the resulting omissions yourself.
Official mesh/texture BSAs are read as dependency sources, never exported.
Assets are copied only from the selected input. Extract custom BSAs beforehand.
Plugin files are not automatically included in output/required/; retain/install
your plugin separately unless it was already part of the input folder.

LIMITATIONS
Static scan is not an in-game proof. Dynamic scripts, implicit engine paths,
voice/FaceGen/LOD generation and external dependencies need review. The NIF
scanner extracts length-prefixed asset strings, not a full block-graph decoder.
Only explicit supported path extensions are recognized: NIF, DDS, TGA, BMP,
KF, EGM, EGT, TRI, WAV, OGG, MP3, LIP, BIK. Unreferenced is not safe-to-delete.
Input must contain asset folders, not be a Meshes or Textures folder itself.
Preview shows first 2,000 files; CSV export includes all files.
Cancelled/failed exports retain INCOMPLETE.txt. Choose new output before retry.
Plugin scan limit 1 GiB; decompressed record/mesh/compared texture limit 256 MiB.
Large master/BSA jobs can require several GiB RAM; no fixed RAM benchmark.
Only free space for copies is needed, not a second full input copy by default.

VALIDATION
9 automated Linux regression tests pass; real Vegas Overhaul ESP parsed
read-only (29,280 records, 1,854 path references), plugin SHA256 unchanged.
Native Windows x64 GUI launcher cross-compiled, version 1.0 and DEP/ASLR checked.
Windows execution and in-game verification were not available.

SOURCE ARCHIVE
Contains app source, tests, native launcher resources and build script.
Runtime remains in the runnable release to avoid duplicating dependencies.
See BUILD.txt and AUDIT.txt. Third-party runtime licenses are in runtime/.

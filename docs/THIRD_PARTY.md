# Third-party notices and dependencies

Paperweek's own source is licensed under MIT; see the root LICENSE.

The actual LVGL build downloads LVGL 9.3.0 from the upstream repository at build time. LVGL's
licence and the licences of included assets/dependencies remain applicable. The packager retains
the LVGL and Emscripten licence text from the actual build dependencies. Its built-in
Montserrat font data originates from the Montserrat project. When publishing compiled LVGL
artifacts, retain the relevant upstream notices/licence files with the distribution. This source
starter does not copy font files from the build environment or vendor LVGL's source tree.

The browser-font preview uses fonts already available on the user's device. It contains no font
file, font download service or font-specific licence grant.

Emscripten is an external build tool with its own LLVM/MIT-related licensing; generated runtime
code may have associated notices. Consult the exact toolchain distribution. The project pins
Emscripten 4.0.14 for repeatability, not because it is claimed to be the latest release.

The **legacy standalone browser adapter** loads Google Identity Services from Google's official endpoint only after explicit preparation
or connection. Google services and APIs have their own terms and data policies. No Google SDK source
is vendored here. The REST adapter is original application code.

Playwright is an optional test dependency; Chromium is an external test browser. Neither is
bundled in the release. GitHub Actions are external automation dependencies referenced in workflow
files; review them and their permissions before enabling workflows in a repository.

References: [LVGL licence](https://github.com/lvgl/lvgl/blob/v9.3.0/LICENCE.txt),
[Montserrat](https://github.com/JulietaUla/Montserrat),
[Emscripten licence](https://github.com/emscripten-core/emscripten/blob/main/LICENSE),
[Google API services policy](https://developers.google.com/terms/api-services-user-data-policy).

## Server dependencies (v0.4)

The container installs pinned FastAPI (MIT), Starlette (BSD-3-Clause), Pydantic (MIT), HTTPX
(BSD-3-Clause), Uvicorn (BSD-3-Clause), cryptography (Apache-2.0/BSD-3-Clause) and OAuthlib
(BSD-3-Clause), along with their transitive dependencies. These are external distributions, not
source copied into this repository. Preserve their installed distribution notices/licences when
redistributing an image. Python and Debian have their own licensing. No model or GPU runtime is
bundled. The backend does not load Google's JavaScript SDK in the display/admin pages; OAuthlib
constructs/parses server OAuth messages and HTTPX communicates with Google endpoints.

Version pins describe the tested environment, not a claim of latest release or security audit.
Review/upkeep of dependencies and base-image digests remains necessary.

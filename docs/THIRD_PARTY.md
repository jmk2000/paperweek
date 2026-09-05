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

Google Identity Services is loaded from Google's official endpoint only after explicit preparation
or connection. Google services and APIs have their own terms and data policies. No Google SDK source
is vendored here. The REST adapter is original application code.

Playwright is an optional test dependency; Chromium is an external test browser. Neither is
bundled in the release. GitHub Actions are external automation dependencies referenced in workflow
files; review them and their permissions before enabling workflows in a repository.

References: [LVGL licence](https://github.com/lvgl/lvgl/blob/v9.3.0/LICENCE.txt),
[Montserrat](https://github.com/JulietaUla/Montserrat),
[Emscripten licence](https://github.com/emscripten-core/emscripten/blob/main/LICENSE),
[Google API services policy](https://developers.google.com/terms/api-services-user-data-policy).

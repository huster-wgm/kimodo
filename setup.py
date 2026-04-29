# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
import shutil
import subprocess
import sys
from pathlib import Path

from setuptools import Extension, find_packages, setup
from setuptools.command.build_ext import build_ext


PYTHON_REQUIRES = ">=3.8"
INSTALL_REQUIRES = [
    "hydra-core>=1.3",
    "omegaconf>=2.3",
    "numpy>=1.23",
    "scipy>=1.10",
    "transformers==5.1.0",
    "urllib3>=2.6.3",
    "boto3",
    "peft>=0.18",
    "einops>=0.7",
    "tqdm>=4.0",
    "packaging>=21.0",
    "pydantic>=2.0",
    "filelock>=3.20.3",
    "gradio>=6.8.0",
    "gradio_client>=1.0",
    "trimesh>=3.21.7",
    "scenepic>=1.1.0",
    "pillow>=9.0",
    "av>=16.1.0",
    "bvhio",
]
EXTRAS_REQUIRE = {
    "demo": ["viser @ git+https://github.com/nv-tlabs/kimodo-viser.git"],
    "soma": ["py-soma-x @ git+https://github.com/NVlabs/SOMA-X.git"],
}
EXTRAS_REQUIRE["all"] = EXTRAS_REQUIRE["demo"] + EXTRAS_REQUIRE["soma"]
ENTRY_POINTS = {
    "console_scripts": [
        "kimodo_gen=kimodo.scripts.generate:main",
        "kimodo_demo=kimodo.demo:main",
        "kimodo_textencoder=kimodo.scripts.run_text_encoder_server:main",
        "kimodo_convert=kimodo.scripts.motion_convert:main",
    ]
}


class CMakeExtension(Extension):
    def __init__(self, name, sourcedir=""):
        super().__init__(name, sources=[])
        self.sourcedir = os.path.abspath(sourcedir)


class CMakeBuild(build_ext):
    def run(self):
        try:
            subprocess.check_output(["cmake", "--version"])
        except OSError as exc:
            raise RuntimeError("CMake must be installed to build this package") from exc

        for ext in self.extensions:
            self.build_extension(ext)

    def build_extension(self, ext):
        extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))
        cmake_args = [
            f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={extdir}",
            f"-DPYTHON_EXECUTABLE={sys.executable}",
        ]

        cfg = "Debug" if self.debug else "Release"
        build_args = ["--config", cfg]
        cmake_args.append(f"-DCMAKE_BUILD_TYPE={cfg}")

        use_mingw = False
        mingw_bin = None

        if sys.platform == "win32":
            generator = os.environ.get("CMAKE_GENERATOR", "")
            if generator:
                cmake_args = ["-G", generator] + cmake_args
                if "mingw" in generator.lower():
                    use_mingw = True
                else:
                    cmake_args.append(f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_{cfg.upper()}={extdir}")
            else:
                try:
                    subprocess.check_output(["g++", "--version"], stderr=subprocess.STDOUT)
                    use_mingw = True
                    cmake_args = ["-G", "MinGW Makefiles"] + cmake_args
                    build_args = []
                except (OSError, subprocess.CalledProcessError):
                    cmake_args.append(f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_{cfg.upper()}={extdir}")

            if use_mingw:
                gxx_path = shutil.which("g++")
                if gxx_path:
                    mingw_bin = Path(gxx_path).parent
        else:
            build_args += ["--", "-j4"]

        env = os.environ.copy()
        env["CXXFLAGS"] = f'{env.get("CXXFLAGS", "")} -DVERSION_INFO=\\"{self.distribution.get_version()}\\"'

        if not os.path.exists(self.build_temp):
            os.makedirs(self.build_temp)

        subprocess.check_call(["cmake", ext.sourcedir] + cmake_args, cwd=self.build_temp, env=env)
        subprocess.check_call(["cmake", "--build", "."] + build_args, cwd=self.build_temp)

        if use_mingw and mingw_bin is not None:
            runtime_libs = [
                "libstdc++-6.dll",
                "libgcc_s_seh-1.dll",
                "libwinpthread-1.dll",
            ]
            extdir_path = Path(extdir)
            extdir_path.mkdir(parents=True, exist_ok=True)
            for lib_name in runtime_libs:
                src_path = mingw_bin / lib_name
                if src_path.exists():
                    shutil.copy2(src_path, extdir_path / lib_name)
                else:
                    self.announce(
                        f"Warning: Expected MinGW runtime DLL '{lib_name}' not found next to g++ (looked in {mingw_bin}). "
                        "The built extension may fail to import if the DLL is not on PATH.",
                        level=3,
                    )


kimodo_packages = find_packages(include=["kimodo", "kimodo.*"])

# When set (e.g. in Docker), do not bundle motion_correction here; it is installed
# separately (e.g. from docker_requirements.txt as ./MotionCorrection) non-editable.
skip_motion_correction = os.environ.get("SKIP_MOTION_CORRECTION_IN_SETUP", "").strip().lower() in ("1", "true", "yes")

if skip_motion_correction:
    packages = kimodo_packages
    package_dir = {}
    ext_modules = []
    cmdclass = {}
else:
    packages = kimodo_packages + ["motion_correction"]
    package_dir = {"motion_correction": "MotionCorrection/python/motion_correction"}
    ext_modules = [CMakeExtension("motion_correction._motion_correction", "MotionCorrection")]
    cmdclass = {"build_ext": CMakeBuild}

setup(
    name="kimodo",
    version="1.0.0",
    description="Kimodo motion generation model",
    python_requires=PYTHON_REQUIRES,
    install_requires=INSTALL_REQUIRES,
    extras_require=EXTRAS_REQUIRE,
    entry_points=ENTRY_POINTS,
    include_package_data=True,
    zip_safe=False,
    packages=packages,
    package_dir=package_dir,
    ext_modules=ext_modules,
    cmdclass=cmdclass,
)

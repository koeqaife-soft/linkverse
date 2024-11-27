from setuptools import setup, Extension
from Cython.Build import cythonize

modules = [
    Extension(
        name="utils_cy.encryption",
        sources=["utils_cy/encryption.pyx"],
    ),
    Extension(
        name="utils_cy.snowflake",
        sources=["utils_cy/snowflake.pyx"],
    )
]

setup(
    name="LinkVerse",
    ext_modules=cythonize(
        modules,
        compiler_directives={'language_level': "3"}
    ),
)

"""
Post-generation script for Protobuf Python files.

This script is designed to be run after generating Python code from .proto
files using the Protocol Buffer compiler (protoc). Its primary purpose is to
fix the import statements within the generated `*_pb2.py` files.

The `protoc` compiler generates absolute import statements, such as:
`import Contract_pb2 as Contract__pb2`

These absolute imports can cause issues when the generated files are part of a
Python package. This script converts them into relative imports by prepending
`from . `, like so:
`from . import Contract_pb2 as Contract__pb2`

This ensures that the generated modules can correctly import their dependencies
within the same package.
"""

import glob
import os


def fix_imports(directory: str):
    """
    Finds all `*_pb2.py` files in a directory and converts their
    Protobuf-related imports to be relative.

    Args:
        directory: The path to the directory containing the generated
                   `*_pb2.py` files.
    """
    for filepath in glob.glob(os.path.join(directory, "*_pb2.py")):
        with open(filepath, "r+") as f:
            lines = f.readlines()
            f.seek(0)
            new_lines = []
            for line in lines:
                if line.startswith("import") and "_pb2" in line:
                    new_lines.append("from . " + line)
                else:
                    new_lines.append(line)
            f.writelines(new_lines)
            f.truncate()


if __name__ == "__main__":
    # The target directory where the generated protobuf files are located.
    fix_imports("ib_async/protobuf")

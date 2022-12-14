# ----------------------------------------------------------------------
# |
# |  __main__.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2022-10-21 08:38:46
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2022-23
# |  Distributed under the Boost Software License, Version 1.0. See
# |  accompanying file LICENSE_1_0.txt or copy at
# |  http://www.boost.org/LICENSE_1_0.txt.
# |
# ----------------------------------------------------------------------
"""Populates cog content in VSCode files."""

import importlib
import inspect
import io
import os
import sys
import textwrap

from pathlib import Path
from typing import Callable, List, Optional, Tuple

import typer

from typer.core import TyperGroup

from Common_Foundation.ContextlibEx import ExitStack
from Common_Foundation.EnumSource import EnumSource
from Common_Foundation import PathEx
from Common_Foundation.Streams.DoneManager import DoneManager, DoneManagerFlags
from Common_Foundation import TextwrapEx

from Common_FoundationEx import ExecuteTasks
from Common_FoundationEx.InflectEx import inflect

from Impl.cogapp import Cog


# ----------------------------------------------------------------------
class NaturalOrderGrouper(TyperGroup):
    # ----------------------------------------------------------------------
    def list_commands(self, *args, **kwargs):  # pylint: disable=unused-argument
        return self.commands.keys()


# ----------------------------------------------------------------------
app                                         = typer.Typer(
    cls=NaturalOrderGrouper,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    pretty_exceptions_enable=False,
)


# ----------------------------------------------------------------------
@app.command("UpdateLaunchFiles", no_args_is_help=True)
def UpdateLaunchFiles(
    input_file_or_directory: Path=typer.Argument(..., exists=True, resolve_path=True, help="Input filename or directory to search for files."),
    single_threaded: bool=typer.Option(False, "--single-threaded", help="Execute with a single thread."),
    quiet: bool=typer.Option(False, "--quiet", help="Reduce the amount of information written to the terminal."),
    verbose: bool=typer.Option(False, "--verbose", help="Write verbose information to the terminal."),
    debug: bool=typer.Option(False, "--debug", help="Write debug information to the terminal."),
) -> None:
    """\
    Updates launch.json using cog.

    Edit 'launch.json' with the code below. `<CogTools name here>` is the name of the
    python file within the `./CogTools` subdirectory that contains the functionality that
    you would like to use.

    Example:
        To populate tests based on functionality in `./CogTools/PopulateTests.py`,
        replace '<CogTools name here>' with 'PopulateTests'.

    `launch.json`:

    {
        ...
        "configurations": [
            ...

            // [[[cog import <CogTools name here>]]]
            // [[[end]]]

            ...
        ]
    }
    """

    with DoneManager.CreateCommandLine(
        output_flags=DoneManagerFlags.Create(verbose=verbose, debug=debug),
    ) as dm:
        search_filename = "launch.json"

        filenames: List[Path] = _GetFiles(dm, input_file_or_directory, search_filename)

        if not filenames:
            dm.WriteLine("No '{}' files were found.\n".format(search_filename))
            return

        tasks = [
            ExecuteTasks.TaskData(str(filename), filename)
            for filename in filenames
        ]

        this_dir = Path(__file__).parent

        cog_tools_dir = this_dir / "CogTools"
        assert cog_tools_dir.is_dir(), cog_tools_dir

        # ----------------------------------------------------------------------
        def TransformStep1(
            context: Path,
            on_simple_status_func: Callable[[str], None],  # pylint: disable=unused-argument
        ) -> Tuple[Optional[int], ExecuteTasks.TransformStep2FuncType]:
            filename = context

            # ----------------------------------------------------------------------
            def Step2(
                status: ExecuteTasks.Status,  # pylint: disable=unused-argument
            ) -> Tuple[None, Optional[str]]:
                # Manually invoke the local cog installation
                sink = io.StringIO()

                cog = Cog()

                cog.setOutput(
                    stdout=sink,
                    stderr=sink,
                )

                result = cog.main(
                    [
                        "custom_cog",       # Fake script name
                        "-c",               # Checksum
                        "-e",               # Warn if a file has no cog code in it
                        "-r",               # Replace
                        "--verbosity=0",
                        "-I", str(cog_tools_dir),
                        str(filename),
                    ],
                )

                output = sink.getvalue()

                if result == 0:
                    lines = output.rstrip().split("\n")

                    if lines[-1].startswith("Warning:"):
                        result = 1

                if result != 0:
                    if "no cog code found in" in output:
                        rows: List[List[str]] = []

                        plugin_dir = PathEx.EnsureDir(Path(__file__).parent / "CogTools")

                        os.environ["__extracting_documentation__"] = "1"
                        with ExitStack(lambda: os.environ.pop("__extracting_documentation__")):
                            for plugin in plugin_dir.iterdir():
                                if not plugin.is_file():
                                    continue

                                sys.path.insert(0, str(plugin.parent))
                                with ExitStack(lambda: sys.path.pop(0)):
                                    mod = importlib.import_module(plugin.stem)
                                    assert mod is not None

                                    rows.append(
                                        [
                                            plugin.stem,
                                            inspect.getdoc(mod) or "",
                                            str(plugin) if dm.capabilities.is_headless else plugin.name,
                                        ],
                                    )

                        # ----------------------------------------------------------------------
                        def DecorateRow(
                            index: int,  # pylint: disable=unused-argument
                            cols: List[str],
                        ) -> List[str]:
                            if not dm.capabilities.is_headless:
                                cols[-1] = TextwrapEx.CreateAnsiHyperLink(
                                    "file:///{}".format((plugin_dir / cols[-1]).as_posix()),
                                    cols[-1],
                                )

                            return cols

                        # ----------------------------------------------------------------------

                        output = textwrap.dedent(
                            """\
                            No cog code was found in '{}'.

                            To use this functionality, add the following cog code in VSCode's 'launch.json' file:

                                // [[[cog import <functionality>]]]
                                // [[[end]]]

                            where '<functionality>' can be one of:

                            {}
                            """,
                        ).format(
                            filename,
                            TextwrapEx.Indent(
                                TextwrapEx.CreateTable(
                                    [
                                        "<functionality>",
                                        "Description",
                                        "Source Code",
                                    ],
                                    rows,
                                    decorate_values_func=DecorateRow,
                                ),
                                4,
                            ),
                        )

                    raise ExecuteTasks.TransformException(
                        textwrap.dedent(
                            """\
                            Cogging '{}' failed with result code '{}'.

                            Output:
                            {}
                            """,
                        ).format(
                            filename,
                            result,
                            TextwrapEx.Indent(output, 4),
                        ),
                    )

                return None, None

            # ----------------------------------------------------------------------

            return None, Step2

        # ----------------------------------------------------------------------

        ExecuteTasks.Transform(
            dm,
            "Cogging",
            tasks,
            TransformStep1,
            quiet=quiet,
            max_num_threads=1 if single_threaded else None,
        )

        if len(tasks) == 1 and dm.result != 0:
            with tasks[0].log_filename.open() as f:
                content = f.read()

            if dm.result < 0:
                func = dm.WriteError
            else:
                func = dm.WriteWarning

            func(content + "\n\n")


# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
def _GetFiles(
    dm: DoneManager,
    input_file_or_directory: Path,
    search_filename: str,
) -> List[Path]:
    if input_file_or_directory.is_file():
        assert input_file_or_directory.name == search_filename
        return [input_file_or_directory, ]

    all_files: List[Path] = []

    with dm.Nested(
        "Searching for '{}' files in '{}'...".format(search_filename, input_file_or_directory),
        lambda: "{} found".format(inflect.no("file", len(all_files))),
        suffix="\n",
    ) as search_dm:
        for root, _, filenames in EnumSource(input_file_or_directory):
            for filename in filenames:
                if filename == search_filename:
                    fullpath = root / filename

                    search_dm.WriteVerbose("'{}' found.".format(fullpath))

                    all_files.append(fullpath)

    return all_files


# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
if __name__ == "__main__":
    app()

#!/usr/bin/env python3
#
#
import time
import unittest
from dataclasses import dataclass
from subprocess import check_call
from threading import Thread, Event
from typing import List, Iterator, Callable, Dict, Optional
from unittest import skip

from branch_restruct import restructure_local, build_tree, Commit, create_temp_branch_name_provider, print_tree
from utils.cmd import output

OUTPUT_LINE_LEN = 100
CONFLICT_RESOLUTION_TIMEOUT_IN_SEC = 5


class GitTestCase(unittest.TestCase):
    def setUp(self):
        self.bar("#")
        self.h2("resetting git")

        self.root_commit = next(output(["git", "log", "--reverse", "--pretty=format:%H"])).strip()
        check_call(["git", "reset", self.root_commit, "--hard"])
        check_call(["git", "checkout", "master"])

        for line in output(["git", "branch", '--format=%(refname:short)']):
            name = line.strip()
            if name == "master":
                continue
            check_call(["git", "branch", "-D", name])

    def run_update_test(self,
                        branches: List[str],
                        build_original: Callable[[], None],
                        update_original: Callable[[], None],
                        fix_updated: Callable[[Commit], None],
                        check: Callable[[], None]):
        self.h2("building original tree")
        build_original()
        original_tree = capture_tree(self.root_commit, *branches)
        self.h3("original tree")
        print_tree(original_tree)

        self.h2("updating original tree")
        update_original()
        self.h3("updated tree")
        print_tree(capture_tree(self.root_commit, *branches))

        self.h2("fixing updated tree")
        fix_updated(original_tree)
        self.h3("fixed tree")
        print_tree(capture_tree(self.root_commit, *branches))

        self.h2("checking fixed tree")
        check()

    def bar(self, char: str):
        print(char * OUTPUT_LINE_LEN)

    def h1(self, line: str):
        print(self.__pad(line, ">", "<"))

    def h2(self, line: str):
        print(self.__pad(line, "=", "="))

    def h3(self, line: str):
        print(self.__pad(line, "-", "-"))

    @staticmethod
    def __pad(line: str, l_char: str, r_char: str) -> str:
        line_len = len(line)
        max_pad_size = OUTPUT_LINE_LEN // min(len(l_char), len(r_char)) + 1
        l_pad = (OUTPUT_LINE_LEN - line_len - 2) // 2
        r_pad = OUTPUT_LINE_LEN - l_pad - line_len - 2
        return (l_char * max_pad_size)[:l_pad] + " " + line + " " + (r_char * max_pad_size)[:r_pad]


class TestLocalUpdateTest(GitTestCase):
    @skip
    def test_amend_branch(self):
        def build_original():
            create_branch(parent="master", name="branch-1", updates=[{"f": ["a", "b"]}])
            create_branch(parent="branch-1", name="branch-2", updates=[{"f": ["a", "b", "c"]}])
            create_branch(parent="branch-2", name="branch-3", updates=[{"f": ["a", "b", "c", "d"]}])

        def update_original():
            amend_branch(name="branch-1", contents={"f": ["_", "a", "b"]})

        def fix_updated(tree: Commit):
            update(tree)

        def check_tree():
            assert_branch(name="branch-1", contents={"f": ["_", "a", "b"]})
            assert_branch(name="branch-2", contents={"f": ["_", "a", "b", "c"]})
            assert_branch(name="branch-3", contents={"f": ["_", "a", "b", "c", "d"]})

        self.run_update_test(
            ["branch-1", "branch-2", "branch-3"],
            build_original,
            update_original,
            fix_updated,
            check_tree
        )

    @skip
    def test_update_branch(self):
        def build_original():
            create_branch(parent="master", name="branch-1", updates=[{"f": ["a", "b"]}])
            create_branch(parent="branch-1", name="branch-2", updates=[{"f": ["a", "b", "c"]}])
            create_branch(parent="branch-2", name="branch-3", updates=[{"f": ["a", "b", "c", "d"]}])

        def update_original():
            update_branch(name="branch-1", updates=[
                {"f": ["_", "a", "b"]},
                {"f": ["_", "-", "a", "b"]},
            ])

        def fix_updated(tree: Commit):
            update(tree)

        def check_tree():
            assert_branch(name="branch-1", contents={"f": ["_", "-", "a", "b"]})
            assert_branch(name="branch-2", contents={"f": ["_", "-", "a", "b", "c"]})
            assert_branch(name="branch-3", contents={"f": ["_", "-", "a", "b", "c", "d"]})

        self.run_update_test(
            ["branch-1", "branch-2", "branch-3"],
            build_original,
            update_original,
            fix_updated,
            check_tree
        )

    @skip
    def test_conflicting_amend_branch(self):
        def build_original():
            create_branch(parent="master", name="branch-1", updates=[{"f": ["a", "b"]}])
            create_branch(parent="branch-1", name="branch-2", updates=[{"f": ["a", "b", "c"]}])
            create_branch(parent="branch-2", name="branch-3", updates=[{"f": ["a", "b", "c", "d"]}])

        def update_original():
            amend_branch(name="branch-1", contents={"f": ["a", "_", "b"]})

        def fix_updated(tree: Commit):
            with ConflictResolver({"f": ["a", "_", "b", "c"]}):
                update(tree)

        def check_tree():
            assert_branch(name="branch-1", contents={"f": ["a", "_", "b"]})
            assert_branch(name="branch-2", contents={"f": ["a", "_", "b", "c"]})
            assert_branch(name="branch-3", contents={"f": ["a", "_", "b", "c", "d"]})

        self.run_update_test(
            ["branch-1", "branch-2", "branch-3"],
            build_original,
            update_original,
            fix_updated,
            check_tree
        )

    def test_multiple_conflicting_amend_branch(self):
        def build_original():
            create_branch(parent="master", name="branch-1", updates=[{"f": ["a", "b"]}])
            create_branch(parent="branch-1", name="branch-2", updates=[{"f": ["a", "b", "c"]}])
            create_branch(parent="branch-2", name="branch-3", updates=[{"f": ["a", "c", "d"]}])

        def update_original():
            amend_branch(name="branch-1", contents={"f": ["a", "_", "b"]})

        def fix_updated(tree: Commit):
            with ConflictResolver({"f": ["a", "_", "b", "c"]},
                                  {"f": ["a", "_", "c", "d"]}):
                update(tree)

        def check_tree():
            assert_branch(name="branch-1", contents={"f": ["a", "_", "b"]})
            assert_branch(name="branch-2", contents={"f": ["a", "_", "b", "c"]})
            assert_branch(name="branch-3", contents={"f": ["a", "_", "c", "d"]})

        self.run_update_test(
            ["branch-1", "branch-2", "branch-3"],
            build_original,
            update_original,
            fix_updated,
            check_tree
        )


@dataclass
class FileContent:
    name: str
    content: List[str]

    def write(self):
        with open(self.name_with_ext(), mode="w", encoding="utf8") as f:
            f.write("\n".join(self.content))

    def check(self):
        with open(self.name_with_ext(), mode="r", encoding="utf8") as f:
            file_lines = [l.rstrip() for l in f.readlines()]
            if file_lines != self.content:
                raise Exception("File contents differ.\n\tExpected: %s\n\tObtained: %s" % (self.content, file_lines))
            print("%s is as expected" % self.short_descr())

    def name_with_ext(self):
        return self.name + ".txt"

    def short_descr(self):
        return self.name + "(" + ",".join(self.content) + ")"


@dataclass(init=False)
class CommitUpdate:
    contents: List[FileContent]

    def __init__(self, contents: Dict[str, List[str]]):
        self.contents: List[FileContent] = [FileContent(key, value) for key, value in contents.items()]

    def subject(self):
        return "|".join((c.short_descr() for c in self.contents))

    def commit(self, subject_prefix: Optional[str] = None):
        for con in self.contents:
            con.write()
        if subject_prefix:
            subject = subject_prefix + self.subject()
        else:
            subject = self.subject()
        commit(subject, amend=False)

    def amend(self):
        for con in self.contents:
            con.write()
        commit(self.subject(), amend=True)

    def check(self):
        for content in self.contents:
            content.check()


def capture_tree(ancestor: str, *branches: str) -> Commit:
    return build_tree(ancestor, [*branches], remote=None)


def update(ideal_tree: Commit):
    restructure_local(ideal_tree,
                      create_temp_branch_name_provider(),
                      CONFLICT_RESOLUTION_TIMEOUT_IN_SEC)


def create_branch(parent: str, name: str, updates: List[Dict[str, List[str]]]):
    checkout(parent)
    checkout(name, create=True)
    for upd in updates:
        CommitUpdate(upd).commit()


def update_branch(name: str, updates: List[Dict[str, List[str]]]):
    checkout(name, create=False)
    for upd in updates:
        CommitUpdate(upd).commit()


def amend_branch(name: str, contents: Dict[str, List[str]]):
    checkout(name, create=False)
    commit_update = CommitUpdate(contents)
    commit_update.amend()


def assert_branch(name: str, contents: Dict[str, List[str]]):
    checkout(name, create=False)
    CommitUpdate(contents).check()


def commit(message: str, amend: bool = False):
    check_call(["git", "add", "."])
    commit_args = ["git", "commit", "-a", "-m", message]
    if amend:
        commit_args.append("--amend")
    check_call(commit_args)


def checkout(branch: str, create: bool = False):
    if create:
        check_call(["git", "checkout", "-b", branch])
    else:
        check_call(["git", "checkout", branch])


class ConflictResolver(Thread):
    def __init__(self, *updates: Dict[str, List[str]]):
        Thread.__init__(self, name="ConflictResolver")
        self.updates = updates
        self.stop_event = Event()

    def run(self):
        updates_it = iter(self.updates)
        while not self.stop_event.is_set():
            self.__check_fix_conflict(updates_it)
            time.sleep(0.1)

    def stop(self):
        self.stop_event.set()

    def __check_fix_conflict(self, updates: Iterator[Dict[str, List[str]]]):
        if self.has_conflict():
            upd = CommitUpdate(next(updates))
            upd.commit(subject_prefix="r:")

    @staticmethod
    def has_conflict() -> bool:
        return next(output(["git", "status", "--porcelain=v1"]), None) is not None

    def __enter__(self):
        self.start()

    def __exit__(self, *args, **kwargs):
        self.stop()
        return False


if __name__ == '__main__':
    unittest.main()

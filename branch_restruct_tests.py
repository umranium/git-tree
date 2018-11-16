#!/usr/bin/env python3
#
# Tests branch_restruct
#
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from subprocess import check_call
from threading import Thread, Event
from typing import List, Iterator

from utils.cmd import output

OUTPUT_LINE_LEN = 100
CONFLICT_RESOLUTION_TIMEOUT_IN_SEC = 5


def main():
    parser = argparse.ArgumentParser(description="branch_restruct")
    subparsers = parser.add_subparsers(dest="subcommand")

    subparsers.add_parser("local_update_test")
    subparsers.add_parser("local_multiple_update_test")
    subparsers.add_parser("local_conflicting_update_test")
    subparsers.add_parser("local_multiple_conflict_update_test")

    args = parser.parse_args()
    subcommand = args.subcommand
    if subcommand == "local_update_amend_test":
        LocalUpdateAmendTest().run()
    elif subcommand == "local_update_commit_test":
        LocalUpdateCommitTest().run()
    elif subcommand == "local_multiple_update_test":
        LocalMultipleUpdateTest().run()
    elif subcommand == "local_conflicting_update_test":
        LocalConflictingUpdateTest().run()
    else:
        LocalUpdateAmendTest().run()
        LocalUpdateCommitTest().run()
        LocalMultipleUpdateTest().run()
        LocalConflictingUpdateTest().run()


class Test:
    def run(self):
        h1(type(self).__name__)
        h2("resetting git")
        reset_git()

        h2("setting up")
        self.given()

        h2("running")
        self.when()

        h2("verifying")
        self.then()

    def given(self):
        pass

    def when(self):
        pass

    def then(self):
        pass


class LocalUpdateAmendTest(Test):
    def given(self):
        create_branch(parent="master", name="branch-1", updates=[
            CommitUpdate(FileContent("f", ["a", "b"]))
        ])

        create_branch(parent="branch-1", name="branch-2", updates=[
            CommitUpdate(FileContent("f", ["a", "b", "c"]))
        ])

        create_branch(parent="branch-2", name="branch-3", updates=[
            CommitUpdate(FileContent("f", ["a", "b", "c", "d"]))
        ])

        push_all()

        amend_branch(name="branch-1", update=CommitUpdate(FileContent("f", ["_", "a", "b"])))

    def when(self):
        update(["branch-1", "branch-2", "branch-3"])

    def then(self):
        assert_branch(name="branch-1", contents=[
            FileContent("f", ["_", "a", "b"])
        ])
        assert_branch(name="branch-2", contents=[
            FileContent("f", ["_", "a", "b", "c"])
        ])
        assert_branch(name="branch-3", contents=[
            FileContent("f", ["_", "a", "b", "c", "d"])
        ])


class LocalUpdateCommitTest(Test):
    def given(self):
        create_branch(parent="master", name="branch-1", updates=[
            CommitUpdate(FileContent("f", ["a", "b"]))
        ])

        create_branch(parent="branch-1", name="branch-2", updates=[
            CommitUpdate(FileContent("f", ["a", "b", "c"]))
        ])

        create_branch(parent="branch-2", name="branch-3", updates=[
            CommitUpdate(FileContent("f", ["a", "b", "c", "d"]))
        ])

        push_all()

        update_branch(name="branch-1", updates=[
            CommitUpdate(FileContent("f", ["_", "a", "b"]))
        ])

    def when(self):
        update(["branch-1", "branch-2", "branch-3"])

    def then(self):
        assert_branch(name="branch-1", contents=[
            FileContent("f", ["_", "a", "b"])
        ])
        assert_branch(name="branch-2", contents=[
            FileContent("f", ["_", "a", "b", "c"])
        ])
        assert_branch(name="branch-3", contents=[
            FileContent("f", ["_", "a", "b", "c", "d"])
        ])


class LocalMultipleUpdateTest(Test):
    def given(self):
        create_branch(parent="master", name="branch-1", updates=[
            CommitUpdate(FileContent("f1", ["a", "b"]))
        ])

        create_branch(parent="branch-1", name="branch-2", updates=[
            CommitUpdate(FileContent("f2", ["a", "b"]))
        ])

        push_all()

        update_branch(name="branch-1", updates=[
            CommitUpdate(FileContent("f1", ["a", "b", "c"])),
            CommitUpdate(FileContent("f1", ["a", "b", "c", "d"]))
        ])

    def when(self):
        update(["branch-1", "branch-2"])

    def then(self):
        assert_branch(name="branch-1", contents=[
            FileContent("f1", ["a", "b", "c", "d"])
        ])
        assert_branch(name="branch-2", contents=[
            FileContent("f1", ["a", "b", "c", "d"]),
            FileContent("f2", ["a", "b"]),
        ])


class LocalConflictingUpdateTest(Test):
    def given(self):
        create_branch(parent="master", name="branch-1", updates=[
            CommitUpdate(FileContent("f", ["a", "b"]))
        ])

        create_branch(parent="branch-1", name="branch-2", updates=[
            CommitUpdate(FileContent("f", ["a", "b", "c"]))
        ])

        push_all()

        amend_branch(name="branch-1", update=CommitUpdate(FileContent("f", ["d", "b", "c"])))

    def when(self):
        with ConflictResolver(CommitUpdate(FileContent("f", ["x", "b", "c"]))):
            update(["branch-1", "branch-2"])

    def then(self):
        assert_branch(name="branch-1", contents=[
            FileContent("f", ["d", "b", "c"])
        ])
        assert_branch(name="branch-2", contents=[
            FileContent("f", ["x", "b", "c"])
        ])


def update(branches: List[str]):
    check_call(["branch_restruct.py",
                "--conflict_resolution_timeout", str(CONFLICT_RESOLUTION_TIMEOUT_IN_SEC),
                "update", *branches])


def reset_git():
    clear_history()
    check_call(["git", "checkout", "master"])
    delete_branches()
    check_call(["git", "push", "--all", "--prune", "--force"])


def delete_branches():
    h2("deleting branches")
    for line in output(["git", "branch", '--format=%(refname:short)']):
        name = line.strip()
        if name == "master":
            continue
        check_call(["git", "branch", "-D", name])


def clear_history():
    h2("reset to first commit")
    line = next(output(["git", "log", "--reverse", "--pretty=format:%H"]))
    check_call(["git", "reset", line.strip(), "--hard"])


@dataclass
class FileContent:
    name: str
    content: List[str]

    def write(self):
        with open(self.name + ".txt", mode="w", encoding="utf8") as f:
            f.write("\n".join(self.content))


@dataclass(init=False)
class CommitUpdate:
    contents: List[FileContent]

    def __init__(self, *contents: FileContent):
        self.contents: List[FileContent] = contents

    def subject(self):
        return "|".join((
            c.name + "(" + ",".join(c.content) + ")"
            for c in self.contents
        ))


def create_branch(parent: str, name: str, updates: List[CommitUpdate]):
    checkout(parent)
    checkout(name, create=True)
    for commit_update in updates:
        for file_content in commit_update.contents:
            file_content.write()
        commit(commit_update.subject())


def update_branch(name: str, updates: List[CommitUpdate]):
    checkout(name, create=False)
    for commit_update in updates:
        for file_content in commit_update.contents:
            file_content.write()
        commit(commit_update.subject())


def amend_branch(name: str, update: CommitUpdate):
    checkout(name, create=False)
    for file_content in update.contents:
        file_content.write()
    commit(update.subject(), amend=True)


def assert_branch(name: str, contents: List[FileContent]):
    checkout(name, create=False)
    for file_content in contents:
        assert_file(file_content.name, file_content.content)


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


def push_all():
    remote = next(output(['git', 'remote']))
    check_call(["git", "push", remote, "--all", "--force", "--quiet"])


def assert_file(file: str, text: List[str]):
    with open(file + ".txt", mode="r", encoding="utf8") as f:
        file_lines = [l.rstrip() for l in f.readlines()]
        if file_lines != text:
            raise Exception("File contents differ.\n\tExpected: %s\n\tObtained: %s" % (text, file_lines))
        print("file %s is as expected" % file)


def h1(line: str):
    print(pad(line, ">", "<"))


def h2(line: str):
    print(pad(line, "=", "="))


def h3(line: str):
    print(pad(line, "-", "-"))


def pad(line: str, l_char: str, r_char: str) -> str:
    line_len = len(line)
    max_pad_size = OUTPUT_LINE_LEN // min(len(l_char), len(r_char)) + 1
    l_pad = (OUTPUT_LINE_LEN - line_len - 2) // 2
    r_pad = OUTPUT_LINE_LEN - l_pad - line_len - 2
    return (l_char * max_pad_size)[:l_pad] + " " + line + " " + (r_char * max_pad_size)[:r_pad]


def has_conflict() -> bool:
    return next(output(["git", "status", "--porcelain=v1"]), None) is not None


class ConflictResolver(Thread):
    def __init__(self, *updates: CommitUpdate):
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

    @staticmethod
    def __check_fix_conflict(updates: Iterator[CommitUpdate]):
        if has_conflict():
            update = next(updates)
            for c in update.contents:
                c.write()
            commit("r:" + update.subject())

    def __enter__(self):
        self.start()

    def __exit__(self, *args, **kwargs):
        self.stop()
        return False


if __name__ == '__main__':
    main()

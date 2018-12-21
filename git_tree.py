#!/usr/bin/env python3
#
# Utility for working on tree/chain branches
#
from __future__ import annotations

import argparse
import time
from collections import deque
from dataclasses import dataclass, field
from subprocess import CalledProcessError
from typing import Optional, List, Iterator, Callable, Dict, Deque, Iterable

from utils.cmd import output
from utils.git import git_ref_hash, git_checkout, git_branch, git_delete_branch, git_rename_branch, git_remote, \
    git_branch_exists, git_common_ancestor, GitLog, git_log_commit, git_log_range, qualify_branch, git_cherrypick

DEFAULT_CONFLICT_RESOLUTION_TIMEOUT_IN_SEC = 24 * 60 * 60


def main():
    parser = argparse.ArgumentParser(description="Utility for working on GIT tree/chain branches")

    parser.add_argument("--conflict_resolution_timeout",
                        help='The amount of time to wait for conflicts to be resolved (in seconds)',
                        type=int,
                        default=DEFAULT_CONFLICT_RESOLUTION_TIMEOUT_IN_SEC)

    subparsers = parser.add_subparsers(dest="subcommand")

    update = subparsers.add_parser(
        "update",
        help="update local structure to reflect remote structure",
        description="Updates local branch tree/chain structure to reflect a remote tree/chain structure"
    )

    update.add_argument(
        "branches",
        metavar='branch-name',
        help='The name of a local branch that is part of the tree/chain (must have a remote branch)',
        nargs='+',
        type=only_local_pushed_branches
    )

    rebase = subparsers.add_parser(
        "rebase",
        help="Rebase a local structure onto a local branch",
        description="Rebase a local branch tree/chain structure onto another local branch"
    )

    rebase.add_argument(
        "--onto",
        metavar='new-base-branch',
        help="Branch to rebase on (default is 'master')",
        default='master',
        type=only_local_branches
    )

    rebase.add_argument(
        "--wo-root",
        help="Skip the root branch in the branch structure to rebase",
        action='store_true',
        default=False
    )

    rebase.add_argument(
        "branches",
        metavar='branch-name',
        help='The name of a local branch that is part of the tree/chain',
        nargs='+',
        type=only_local_branches
    )

    args = parser.parse_args()
    subcommand = args.subcommand
    if subcommand == "update":
        process_update(args.branches, args.conflict_resolution_timeout)
    elif subcommand == "rebase":
        process_rebase(args.branches, args.onto, args.wo_root, args.conflict_resolution_timeout)


def only_local_pushed_branches(branch_name: str) -> Optional[str]:
    if not git_branch_exists(branch_name, remote=False):
        raise argparse.ArgumentTypeError("'%s' is not a name of an existing local branch" % branch_name)
    if not git_branch_exists(branch_name, remote=True):
        raise argparse.ArgumentTypeError("'%s' does not have a remote branch" % branch_name)
    return branch_name


def only_local_branches(branch_name: str) -> Optional[str]:
    if not git_branch_exists(branch_name, remote=False):
        raise argparse.ArgumentTypeError("'%s' is not a name of an existing local branch" % branch_name)
    return branch_name


@dataclass
class Commit:
    full_hash: str
    subject: str = ""
    refs: List[str] = field(default_factory=list)
    is_merger: bool = False
    children: List['Commit'] = field(default_factory=list)

    @staticmethod
    def from_log(git_log: GitLog) -> Commit:
        return Commit(full_hash=git_log.full_hash,
                      subject=git_log.subject,
                      refs=git_log.refs)

    def find_ref(self, ref: str) -> Optional['Commit']:
        def is_ref(commit: Commit):
            return ref in commit.refs

        return next(self.__find_descendant(is_ref), None)

    def find_commit(self, full_hash: str) -> Optional['Commit']:
        def is_commit(commit: Commit):
            return commit.full_hash == full_hash

        return next(self.__find_descendant(is_commit), None)

    def all_nodes(self) -> Iterator[Commit]:
        def all_true(_):
            return True

        yield from self.__find_descendant(all_true)

    def first_ref(self) -> Optional[str]:
        return next(iter(self.refs), None)

    def sorted_children(self) -> Iterable[Commit]:
        return sorted(self.children, key=lambda x: x.full_hash)

    def __str__(self) -> str:
        return str({'hash': self.full_hash, 'refs': self.refs})

    def __hash__(self) -> int:
        return hash(self.full_hash)

    def __find_descendant(self, check: Callable[['Commit'], bool]) -> Iterator['Commit']:
        if check(self):
            yield self
        for c in self.children:
            yield from c.__find_descendant(check)


@dataclass
class Segment:
    start_ref: str
    start_full_hash: str
    end_ref: str
    end_full_hash: str


def process_update(branches: List[str], conflict_resolution_timeout_secs: int):
    remote = git_remote()
    remote_branches = [qualify_branch(b, remote) for b in branches]
    ancestor = git_common_ancestor(*branches, *remote_branches)
    remote_tree = build_tree(ancestor, remote_branches, branches)
    verify_tree(remote_tree)
    local_tree = build_tree(ancestor, branches)
    verify_tree(local_tree)

    print("Remote tree:")
    print_tree(remote_tree)

    print("Local tree:")
    print_tree(local_tree)

    update_local_struct(remote_tree,
                        create_temp_branch_name_provider(),
                        conflict_resolution_timeout_secs)

    print("Updated local tree:")
    print_tree(build_tree(ancestor, branches))


def update_local_struct(required_tree: Commit,
                        temp_ref_name_provider: Callable[[str], str],
                        conflict_resolution_timeout_secs: int):
    old_to_new_name_map: Dict[str, str] = {}

    for segment in bfs_segments(required_tree):
        print("segment", segment)
        old_ref = segment.end_ref
        if old_ref in old_to_new_name_map:
            log_cmd("git checkout %s" % old_to_new_name_map[old_ref])
            git_checkout(old_to_new_name_map[old_ref])
        else:
            new_ref = temp_ref_name_provider(old_ref)
            if segment.start_ref in old_to_new_name_map:
                start_ref = old_to_new_name_map[segment.start_ref]
            else:
                start_ref = segment.start_ref
            old_to_new_name_map[old_ref] = new_ref
            log_cmd("git branch -b %s %s" % (new_ref, start_ref))
            git_branch(new_ref, start_ref)

        git_cherrypick_range(segment, conflict_resolution_timeout_secs)

    for old_ref in old_to_new_name_map.keys():
        git_delete_branch(old_ref)
    for old_ref, new_ref in old_to_new_name_map.items():
        git_rename_branch(new_ref, old_ref)


def process_rebase(branches: List[str],
                   onto: str,
                   without_root: bool,
                   conflict_resolution_timeout_secs: int):
    if without_root:
        rebase_without_root(branches,
                            onto,
                            create_temp_branch_name_provider(),
                            conflict_resolution_timeout_secs,
                            debug_tree=True)
    else:
        rebase_with_root(branches,
                         onto,
                         create_temp_branch_name_provider(),
                         conflict_resolution_timeout_secs,
                         debug_tree=True)


def rebase_with_root(branches: List[str],
                     base_branch: str,
                     temp_ref_name_provider: Callable[[str], str],
                     conflict_resolution_timeout_secs: int,
                     debug_tree: bool):
    branch_ancestor = git_common_ancestor(*branches, base_branch)
    local_tree = build_tree(branch_ancestor, branches)
    verify_tree(local_tree)

    if debug_tree:
        print("Local tree:")
        print_tree(local_tree)

    old_to_new_name_map: Dict[str, str] = {}

    for segment in bfs_segments(local_tree):
        old_ref = segment.end_ref
        if old_ref in old_to_new_name_map:
            log_cmd("git checkout %s" % old_to_new_name_map[old_ref])
            git_checkout(old_to_new_name_map[old_ref])
        else:
            new_ref = temp_ref_name_provider(old_ref)
            if segment.start_full_hash == local_tree.full_hash:  # is root
                start_ref = base_branch
            elif segment.start_ref in old_to_new_name_map:
                start_ref = old_to_new_name_map[segment.start_ref]
            else:
                start_ref = segment.start_ref
            old_to_new_name_map[old_ref] = new_ref
            log_cmd("git branch -b %s %s" % (new_ref, start_ref))
            git_branch(new_ref, start_ref)

        git_cherrypick_range(segment, conflict_resolution_timeout_secs)

    for old_ref in old_to_new_name_map.keys():
        git_delete_branch(old_ref)
    for old_ref, new_ref in old_to_new_name_map.items():
        git_rename_branch(new_ref, old_ref)

    if debug_tree:
        print("Updated local tree:")
        print_tree(build_tree(branch_ancestor, branches))


def rebase_without_root(branches: List[str],
                        base_branch: str,
                        temp_ref_name_provider: Callable[[str], str],
                        conflict_resolution_timeout_secs: int,
                        debug_tree: bool):
    branch_ancestor = git_common_ancestor(*branches)
    local_tree = build_tree(branch_ancestor, branches)
    verify_tree(local_tree)

    if debug_tree:
        print("Local tree:")
        print_tree(build_tree(git_common_ancestor(*branches, base_branch), branches + [base_branch]))

    old_to_new_name_map: Dict[str, str] = {}

    for segment in bfs_segments(local_tree):
        print(segment)
        old_ref = segment.end_ref
        if old_ref in old_to_new_name_map:
            log_cmd("git checkout %s" % old_to_new_name_map[old_ref])
            git_checkout(old_to_new_name_map[old_ref])
        else:
            new_ref = temp_ref_name_provider(old_ref)
            if segment.start_full_hash == local_tree.full_hash:  # is root
                start_ref = base_branch
            elif segment.start_ref in old_to_new_name_map:
                start_ref = old_to_new_name_map[segment.start_ref]
            else:
                start_ref = segment.start_ref
            old_to_new_name_map[old_ref] = new_ref
            log_cmd("git branch -b %s %s" % (new_ref, start_ref))
            git_branch(new_ref, start_ref)

        git_cherrypick_range(segment, conflict_resolution_timeout_secs)

    for old_ref in old_to_new_name_map.keys():
        git_delete_branch(old_ref)
    for old_ref, new_ref in old_to_new_name_map.items():
        git_rename_branch(new_ref, old_ref)

    if debug_tree:
        print("Updated local tree:")
        print_tree(build_tree(git_common_ancestor(*branches, base_branch), branches + [base_branch]))


def verify_tree(root: Commit):
    for c in root.all_nodes():
        if c.is_merger:
            raise Exception("Commit %s is a merge. " % c.full_hash +
                            "Merge commits are not supported.")
        if len(c.refs) > 1:
            raise Exception("Commit %s has references [%s]. " % (c.full_hash, ",".join(sorted(c.refs))) +
                            "Commits with multiple references are not supported.")


def build_tree(ancestor: str, branches: List[str], branch_names: Optional[List[str]] = None) -> Commit:
    if not branch_names:
        branch_names = branches

    hash_to_log_map: Dict[str, GitLog] = {ancestor: git_log_commit(ancestor, skip_parent_hashes=True)}

    # assign branch names to ancestor
    for name, branch in zip(branch_names, branches):
        if git_ref_hash(branch) == ancestor:
            hash_to_log_map[ancestor].refs.append(name)

    for name, branch in zip(branch_names, branches):
        commit_range_details = list(git_log_range(ancestor, branch))

        # add logs to map if not already existing
        for details in commit_range_details:
            if details.full_hash not in hash_to_log_map:
                hash_to_log_map[details.full_hash] = details

        # assign branch name
        if commit_range_details:
            last_hash = commit_range_details[0].full_hash
            hash_to_log_map[last_hash].refs.append(name)

    # create commits and invert hierarchy
    commits: Dict[str, Commit] = {
        d.full_hash: Commit.from_log(d)
        for d in hash_to_log_map.values()
    }

    for c in hash_to_log_map.values():
        commit = commits[c.full_hash]
        if len(c.parent_hashes) > 1:
            commit.is_merger = True
        for p in c.parent_hashes:
            parent = commits[p]
            parent.children.append(commit)

    return commits[ancestor]


def bfs_segments(root: Commit) -> Iterator[Segment]:
    """
    Breadth-first search through the tree to extract segments
    """

    @dataclass
    class Entry:
        commit: Commit
        seg_start_ref: Optional[str]
        seg_start_hash: Optional[str]

        @staticmethod
        def root(commit: Commit) -> Entry:
            return Entry(commit=commit,
                         seg_start_ref=commit.first_ref(),
                         seg_start_hash=commit.full_hash)

        @staticmethod
        def child(commit: Commit, par: Entry) -> Entry:
            if commit.refs:
                return Entry(commit=commit,
                             seg_start_ref=commit.first_ref(),
                             seg_start_hash=commit.full_hash)
            else:
                return Entry(commit=commit,
                             seg_start_ref=par.seg_start_ref,
                             seg_start_hash=par.seg_start_hash)

    queue: Deque[Entry] = deque()

    queue.append(Entry.root(root))
    while queue:
        parent = queue.popleft()
        for c in parent.commit.children:
            new_entry = Entry.child(c, parent)
            queue.append(new_entry)
            if new_entry.seg_start_ref and parent.seg_start_ref and new_entry.seg_start_ref != parent.seg_start_ref:
                yield Segment(
                    start_ref=parent.seg_start_ref,
                    start_full_hash=parent.seg_start_hash,
                    end_ref=new_entry.seg_start_ref,
                    end_full_hash=new_entry.seg_start_hash
                )
            elif new_entry.seg_start_ref and parent.seg_start_hash == root.full_hash:
                yield Segment(
                    start_ref=root.first_ref(),
                    start_full_hash=root.full_hash,
                    end_ref=new_entry.seg_start_ref,
                    end_full_hash=new_entry.seg_start_hash
                )


def git_cherrypick_range(segment: Segment, conflict_resolution_timeout_secs: int):
    commits = [log.full_hash for log in git_log_range(segment.start_full_hash, segment.end_ref)]
    for commit in reversed(commits):
        try:
            log_cmd("cherry-pick %s" % commit)
            git_cherrypick(commit)
        except CalledProcessError as e:
            if not has_conflicting_files():
                raise e
            print("Conflict detected, please resolve to continue....")
            wait_for_conflict_resolution(conflict_resolution_timeout_secs, e)


def has_conflicting_files() -> bool:
    return next(conflicting_files(), None) is not None


def conflicting_files() -> Iterator[List[str]]:
    for line in output(["git", "status", "--porcelain=v1"]):
        yield line.split("\t")


def wait_for_conflict_resolution(timeout_secs: int, base_error: Exception):
    start = time.time()
    while has_conflicting_files():
        if time.time() - start > timeout_secs:
            raise RuntimeError("Conflict not resolved in time", base_error)
        time.sleep(0.1)


def create_temp_branch_name_provider() -> Callable[[str], str]:
    ref_index = [0]

    # noinspection PyUnusedLocal
    def provider(old_name: str) -> str:
        while True:
            name = "%s-tmp-%d" % (old_name, ref_index[0])
            if git_branch_exists(name, remote=False):
                ref_index[0] = ref_index[0] + 1
                continue
            return name

    return provider


def print_tree(root: Commit, tabs: int = 0):
    print("    " * tabs, root.full_hash, root.subject, root.refs)
    for c in root.children:
        print_tree(c, tabs + 1)


def log_cmd(cmd: str):
    print("$", cmd)


if __name__ == '__main__':
    main()

import re
from dataclasses import dataclass, field
from subprocess import check_call
from typing import List, Iterator, Optional

from utils.cmd import output, log_cmd


def git_checkout(ref: str, log: bool = False):
    cmd = ["git", "checkout", ref]
    if log:
        log_cmd(cmd)
    check_call(cmd)


def git_branch(name: str, ref: str, log: bool = False):
    cmd = ["git", "checkout", "-b", name, ref]
    if log:
        log_cmd(cmd)
    check_call(cmd)


def git_remote() -> str:
    """
    :return: Name of the first remote
    """
    return next(output(['git', 'remote']), None)


def git_common_ancestor(*commits: str) -> str:
    """
    :param commits: list of hash or reference to commits
    :return: the hash of the common ancestor of the commits given
    """
    return next(output(['git', 'merge-base', '--octopus', *commits]))


def git_ref_hash(reference: str) -> str:
    """
    :return: the hash of the commit for a tag or branch
    """
    return next(output(['git', 'rev-parse', reference]))


def git_delete_branch(ref: str):
    check_call(["git", "branch", "-D", ref])


def git_rename_branch(from_name: str, to_name: str):
    check_call(["git", "branch", "-m", from_name, to_name])


def git_branch_exists(branch_name: str, remote: bool = False) -> bool:
    """
    :return: Checks whether the git branch with the name given exists
    """
    if remote:
        args = ['git', 'branch', '--list', '-r', qualify_branch(branch_name, git_remote())]
    else:
        args = ['git', 'branch', '--list', branch_name]
    branch_found = next(output(args), None)
    return branch_found is not None


def git_cherrypick(commitish: str, log: bool = False):
    cmd = ["git", "cherry-pick", commitish]
    if log:
        log_cmd(cmd)
    check_call(cmd)


def git_push(remote: str, local_ref: str, remote_ref: Optional[str], force: bool, log: bool = False):
    if remote_ref:
        full_ref = "%s:%s" % (local_ref, remote_ref)
    else:
        full_ref = local_ref
    cmd = ["git", "push", remote, full_ref]
    if force:
        cmd.append("--force")
    if log:
        log_cmd(cmd)
    check_call(cmd)


@dataclass
class GitLog:
    full_hash: str
    subject: str = ""
    parent_hashes: List[str] = field(default_factory=list)
    refs: List[str] = field(default_factory=list)

    def __hash__(self) -> int:
        return hash(self.full_hash)

    @staticmethod
    def git_log_format() -> str:
        return "%H|%P|%s"

    @staticmethod
    def parse(line: str, skip_parent_hashes: bool = False) -> 'GitLog':
        (full_hash, combined_parent_hashes, subject) = line.split("|", maxsplit=2)
        if skip_parent_hashes:
            parent_hashes = []
        else:
            parent_hashes = re.split("\s+", combined_parent_hashes)
            parent_hashes = [p for p in parent_hashes if p]  # filter empty
        return GitLog(full_hash=full_hash,
                      parent_hashes=parent_hashes,
                      subject=subject)


def git_log_range(start_commitish: str, end_commitish: str) -> Iterator[GitLog]:
    """
    Returns all commits within the given range
    :param start_commitish: First (earliest) commit to iterate through (not inclusive)
    :param end_commitish: Last (latest) commit to iterate through (inclusive)
    :return:
    """
    for line in output(["git", "log", "%s..%s" % (start_commitish, end_commitish),
                        "--pretty=format:%s" % GitLog.git_log_format()]):
        yield GitLog.parse(line)


def git_log_commit(commitish: str, skip_parent_hashes: bool = False) -> GitLog:
    line = next(output(["git", "log", commitish, "--pretty=format:%s" % GitLog.git_log_format()]))
    return GitLog.parse(line, skip_parent_hashes)


def qualify_branch(branch: str, remote: Optional[str]) -> str:
    if remote:
        return '%s/%s' % (remote, branch)
    else:
        return branch

# git-tree

Utility for working on GIT tree/chain branches 


## Usage


### To fix a local updated branch structure to reflect the remote branch structure  

```bash
git_tree update branch-name [branch-name ...]
```

#### After updating a local branch

For example:

You have the following branch structure:

```
master    base-branch      branch-1
|         |                |
c0 <---- c1 <---- c2 <---- c3
             \
              `- c4
                 |
                 branch-2
```

after pushing this structure to remote, you update `base-branch`:

```
                  base-branch      
                  |
master        ,- c5        branch-1
|            /             |
c0 <---- c1 <---- c2 <---- c3
             \
              `- c4
                 |
                 branch-2
```

At this point, `branch-1` and `branch-2` will not contain the new changes on `base-branch`.
To rebuild the previous branch structure where `branch-1` and `branch-2` are based on `base-branch` and contains all the updated changes run the command:

```bash
git_tree update base-branch branch-1 branch-2

```

End result:
```
master             base-branch      branch-1
|                  |                |
c0 <---- c1 <---- c5 <---- c2 <---- c3
                      \
                       `- c4
                          |
                          branch-2
```

#### After amending a local branch

For example:

You have the same branch structure as above:

```
master    base-branch      branch-1
|         |                |
c0 <---- c1 <---- c2 <---- c3
             \
              `- c4
                 |
                 branch-2
```

after pushing this structure to remote, you update `base-branch` as before but you amend the branch:

```
          base-branch      
master    |
|     ,-- c5        
|    /             
c0 <-              branch-1
     \             |
      `-- c1 <---- c2 <---- c3
              \
               `- c4
                  |
                  branch-2
```

At this point, `branch-1` and `branch-2` (as before) will not contain the new changes on `base-branch`.
To rebuild the previous branch structure where `branch-1` and `branch-2` are based on `base-branch` and contains all the updated changes run the command:

```bash
git_tree update base-branch branch-1 branch-2

```

End result:
```
master   base-branch       branch-1
|        |                 |
c0 <---- c5 <---- c2 <---- c3
                      \
                       `- c4
                          |
                          branch-2
```

### To "rebase" a local branch structure when the remote get's updated   

```bash
git_tree rebase --onto base-branch branch-name [branch-name ...]
```

For example:

You have the following branch structure (yeah same one again):

```
master    base-branch      branch-1
|         |                |
c0 <---- c1 <---- c2 <---- c3
             \
              `- c4
                 |
                 branch-2
```

`master` gets updated remotely.
After pulling the changes, you have the following structure:

```
         master
         |
     ,-- c5
    /
c0 <-    base-branch       branch-1
    \    |                 |
     `-- c1 <---- c2 <---- c3
             \
              `- c4
                 |
                 branch-2
```

At this point, remote doesn't have the original branch structure, and neither does local.
To get the original structure:
 
```bash
git_tree rebase --onto master base-branch branch-1 branch-2
```

End result:
```
         master   base-branch       branch-1
         |        |                 |
c0 <---- c5 <---- c1 <---- c2 <---- c3
                      \
                       `- c4
                          |
                          branch-2
```

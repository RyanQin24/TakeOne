# Analysis 4 - determinism of Tree B compiles (three separate processes)

- run1: plan sha256 2ed5919c146b1eeb2a90257999ae303b4ef985f723a94d8d03ff13d8486480e6  bytes 7101578  compile_s 93.88  export sha256 312a334f59eafea859ce8c0fd635d0af10586337ff256a0c3286286f9a0486d3
- run2: plan sha256 698344d8b67316ef2c5f065a100dda4c8c076e78bb4c407b62c689c0f3efc3d4  bytes 7101578  compile_s 64.46  export sha256 b221f1b463076d598a884507cbef3c7c1ce6e9525b36444c3bc56877d789facb
- run3: plan sha256 dd52cb7032e7384381397ac9f46ba7cf8b003f8e835fb7b091b324458ea87fb7  bytes 7101578  compile_s 86.26  export sha256 43a859e4fe47dda27c3d7d22a92a7ace0d012949ee7b16f24c629a4f0978ea10

After removing plan['compile_seconds'] (wall-clock bookkeeping stored inside the plan artifact):
- run1: sha256 79e471f719a84bdfddf969c60a294061272d349d3c9c207e3391c1b2084f7e6c
- run2: sha256 79e471f719a84bdfddf969c60a294061272d349d3c9c207e3391c1b2084f7e6c
- run3: sha256 79e471f719a84bdfddf969c60a294061272d349d3c9c207e3391c1b2084f7e6c

## run1 vs run2: 0 differing leaves (first 40 shown)

byte-identical after removing compile_seconds

## run1 vs run3: 0 differing leaves (first 40 shown)

byte-identical after removing compile_seconds

## run2 vs run3: 0 differing leaves (first 40 shown)

byte-identical after removing compile_seconds

## Differences by top-level key (run1 vs run2, unlimited)


## Differences by field family (run1 vs run2)

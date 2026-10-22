== A. pass@1 vs pass^2 (both attempts solve): do rankings flip? cells with k2 runs
  mini-swe-agent  moe-a3b          c=16 H100!  pass@1 0.50  pass^2 0.42  pass@2 0.58  consistency 0.83 n=36
  mini-swe-agent  moe-a3b          c=32 H100!  pass@1 0.47  pass^2 0.42  pass@2 0.53  consistency 0.88 n=36
  mini-swe-agent  b200             c=32 B200   pass@1 0.46  pass^2 0.42  pass@2 0.50  consistency 0.91 n=36
  mini-swe-agent  h200             c=32 H200   pass@1 0.44  pass^2 0.36  pass@2 0.53  consistency 0.81 n=36
  mini-swe-agent  defaults         c=16 H100!  pass@1 0.44  pass^2 0.39  pass@2 0.50  consistency 0.88 n=36
  mini-swe-agent  no-thinking      c=32 H100!  pass@1 0.39  pass^2 0.31  pass@2 0.47  consistency 0.79 n=36
  mini-swe-agent  defaults-2x-time c=32 H100!  pass@1 0.36  pass^2 0.28  pass@2 0.44  consistency 0.77 n=36
  mini-swe-agent  defaults         c=32 H100!  pass@1 0.35  pass^2 0.22  pass@2 0.47  consistency 0.64 n=36
  mini-swe-agent  defaults         c=48 H100!  pass@1 0.35  pass^2 0.25  pass@2 0.44  consistency 0.72 n=36
  mini-swe-agent  spec-mtp         c=32 H100!  pass@1 0.33  pass^2 0.25  pass@2 0.42  consistency 0.75 n=36
  mini-swe-agent  defaults         c=64 H100!  pass@1 0.26  pass^2 0.17  pass@2 0.36  consistency 0.63 n=36
  terminus-2      b200             c=32 B200   pass@1 0.56  pass^2 0.44  pass@2 0.67  consistency 0.80 n=36
  terminus-2      no-thinking      c=32 H100!  pass@1 0.49  pass^2 0.44  pass@2 0.53  consistency 0.91 n=36
  terminus-2      defaults-2x-time c=32 H100!  pass@1 0.47  pass^2 0.36  pass@2 0.58  consistency 0.76 n=36
  terminus-2      h200             c=32 H200   pass@1 0.42  pass^2 0.33  pass@2 0.50  consistency 0.80 n=36
  terminus-2      moe-a3b          c=16 H100!  pass@1 0.42  pass^2 0.31  pass@2 0.53  consistency 0.73 n=36
  terminus-2      defaults         c=16 H100!  pass@1 0.42  pass^2 0.33  pass@2 0.50  consistency 0.80 n=36
  terminus-2      defaults         c=32 H100!  pass@1 0.40  pass^2 0.29  pass@2 0.51  consistency 0.72 n=72
  terminus-2      spec-mtp         c=32 H100!  pass@1 0.39  pass^2 0.25  pass@2 0.53  consistency 0.64 n=36
  terminus-2      moe-a3b          c=32 H100!  pass@1 0.39  pass^2 0.31  pass@2 0.47  consistency 0.79 n=36
  terminus-2      defaults         c=48 H100!  pass@1 0.33  pass^2 0.22  pass@2 0.44  consistency 0.67 n=36
  terminus-2      defaults         c=64 H100!  pass@1 0.22  pass^2 0.14  pass@2 0.31  consistency 0.63 n=36
  terminus-2: 1 of 55 config pairs swap order between pass@1 and pass^2
  mini-swe-agent: 1 of 55 config pairs swap order between pass@1 and pass^2

== B. How many tasks to rank two setups correctly? (bootstrap subsets of tasks, big cells)
  terminus-2, true gap 3-7 pts (20 pairs), one run each, right order: 10 tasks: 62%, 20 tasks: 66%, 36 tasks: 71%, 100 tasks: 84%
  terminus-2, true gap 8-15 pts (22 pairs), one run each, right order: 10 tasks: 75%, 20 tasks: 85%, 36 tasks: 92%, 100 tasks: 99%
  mini-swe-agent, true gap 3-7 pts (25 pairs), one run each, right order: 10 tasks: 63%, 20 tasks: 68%, 36 tasks: 75%, 100 tasks: 86%
  mini-swe-agent, true gap 8-15 pts (37 pairs), one run each, right order: 10 tasks: 77%, 20 tasks: 85%, 36 tasks: 91%, 100 tasks: 99%

== C. Silent failures: agent finished (no time-out) but the answer was wrong
  terminus-2: of 792 trials that ended on their own, 18% were wrong; median steps wrong 13 vs right 10; median agent time wrong 515s vs right 393s
  mini-swe-agent: of 608 trials that ended on their own, 18% were wrong; median steps wrong 28 vs right 15; median agent time wrong 509s vs right 396s

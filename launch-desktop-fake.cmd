@echo off
rem Teacher UI with instant fake marking: no marking model calls.
rem Open a COPY of a scan (e.g. fake_test_pile2\_continuous.pdf), never a real task.
call "%~dp0Marking App.cmd" --fake-marking %*

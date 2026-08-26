# W8e — two W10 design rulings and one sequencing constraint

**Archived prompt. Intent, not state — `BUILD_PROGRESS.md` is the record of what is built.**
Given 2026-08-26. Records only — no code, no migration, no server step.

---

Record two W10 design rulings and one sequencing constraint. Records only — no code, no migration, no server step.

Ruling 1 — typed answers, split by card type (#157).

production and cloze cards take a typed answer, graded through the existing grading.equivalence_key / distinct_answers seam. recognition cards keep W6's self-mark, because the answer is a meaning and a meaning cannot be machine-graded against a typed string.

The reason, from use: a card that shows the answer on a tap and asks the learner to grade themselves cannot distinguish recall from recognition, and that distinction is the whole difference between knowing a word and thinking you know it. Recording that this was noticed by the operator using the reviewer, not by any gate.

Ruling 2 — checkpoints stay pure grammar in W10 (#170).

W8d gave all 12 checkpoint items to grammar. Do not re-source vocabulary items from the learner's FSRS due cards in W10. Revisit at W13, when video capture has made the deck large enough to draw from — the deck is 29 cards today and W8b removed 14 of them. Re-target #170 from W11 to W13 with that trigger stated as deck size, not a date.

Both rulings: assistant-recommended, operator-accepted. Record the authorship the way the five W8c glosses were recorded — the distinction between authored and accepted matters when someone later asks why.

The sequencing constraint — file it so W10 cannot be planned around it.

W10 must not be planned until #164 is settled. W10 generates items against each unit's grammar targets and their Murphy citations, which is precisely the surface #164's escalation clause names — "to high on the first slice that shows a citation to a learner." Three citations are known to contradict each other (Murphy 19–20 across units 3 and 9; Murphy 38 across units 12 and 17), and #164 records that a wrong citation fails silently, because the learner assumes the book is correct and concludes they are confused.

Note the constraint the record already established: a uniform edition offset cannot explain a collision, since it maps equal numbers to equal numbers. So the edition question and the contradictions are independent, and settling the edition does not clear them.

W8 check 4 is the unblocking step — one pass with Murphy: does unit 25 teach past perfect, does 38 teach must/can't, do 36–37 teach might/may/could, which edition. It stays part-run and blocked on the book, carried with all four questions.

Do not start W9 or W10.

# WISHENKA-311: Browser checks stay green beside other browser checks

## Goals

A person adding a wish, and a person opening an older list from viewing
history, already get the outcomes below when those checks run one after
another. The same outcomes must still be shown as passed when other browser
checks run at the same time.

Today the two checks fail only under that parallel load and pass when they
run sequentially. A red result that appears only because neighbors are
running is a false alarm. Maintainers then cannot tell a real break in
quick add or viewing history from a check that gave up on the clock.

This is a Debt item (3 points, Medium, label `tech-debt`), follow-up 4 from
WISHENKA-294. Implementation language: Python.

## User Stories

- As an **owner** using quick add, while the add is still waiting for an
  answer I see the form as busy and I cannot submit it again. When the wish
  is saved, the form is usable again and the new wish is on the list.
- As a **person using viewing history**, I open an older list and that list
  becomes the most recently viewed. I can leave that list and return home.
- As a **maintainer**, I run these two checks together with other browser
  checks and both stay green. A run that only passes them one after another
  does not give me that trust.

## Definition of Done

1. **Busy quick add.** While a quick add is still in flight, the form is
   marked busy and the add control cannot be used. After the answer arrives,
   the form is usable again and the new wish is on the list.
2. **History order and return home.** Opening an older viewing-history entry
   moves that list to the top. From history, Back returns to the Mini App
   home, and the screen reports no console errors.
3. **Parallel proof.** These two checks pass while other browser checks run
   beside them:
   - `tests/test_cross_screen_comfort_browser.py::test_htmx_pending_request_marks_the_form_busy`
   - `tests/test_history_screen_browser.py::`
     `test_control_opening_an_entry_moves_it_to_the_top_and_navigation_works`
4. **Sequential is not enough.** Each check passing when run alone, or when
   the browser checks run one after another, does not close this task.
5. **The clock is not the fix.** The busy-form check currently stops after a
   fixed wait of 3 seconds. Done means the check settles on a condition it
   can observe, or the in-flight request stays held until the check releases
   it. Giving that same wait more seconds does not count as done.
6. **Left to other tasks.** WISHENKA-357 is not fixed here. The full suite
   that stops at 600 seconds (WISHENKA-285) is not fixed here and is not the
   proof this task requires. `wishenka/web/static/app.js` does not gain the
   substring `receipt`.

## Task Description

### Problem

The busy quick-add check and the viewing-history check guard two rules that
already hold in a sequential run. Under parallel browser load those checks
are reported failed. The failure is the check giving up while neighbors are
running, not a new product rule. WISHENKA-294 recorded this as non-blocking
follow-up 4. This step states the outcome and does not choose the change.

### Scope

- The busy quick-add rule and the viewing-history rule in the Definition of
  Done stay true.
- A maintainer sees the two named checks pass while other browser checks run
  beside them.
- The check decides from an observed condition, or from a request that stays
  held until the check lets it finish.

### Constraints

- Do not accept a sequential-only pass as the close of this task.
- Do not lengthen a wall-clock timeout and call that the fix.
- Do not fix WISHENKA-357 in this task.
- Do not fix the 600-second full suite (WISHENKA-285) in this task, and do
  not treat that suite as the required proof.
- Do not edit `wishenka/web/static/app.js` to add the substring `receipt`.

### Non-goals

- A new quick-add field, a new history screen, or a change to who may add a
  wish or open a list.
- Making a slow machine pass by waiting longer on the clock.
- Repair of WISHENKA-357 or WISHENKA-285.
- Any edit of `wishenka/web/static/app.js` that introduces `receipt`.
- Other failing checks from the sprint.

### Main entities

- **Owner** — the person who adds a wish from the quick-add bar on a list
  they can edit.
- **Quick-add form** — the bar used to add one wish. While the add is in
  flight the form is busy and the control cannot be used again. After the
  answer, the form is usable and the new wish is visible.
- **Wish** — the item that appears on the list once the add has finished.
- **Viewing-history entry** — a list the person opened before. Opening an
  older entry makes that list the most recently viewed.
- **Mini App home** — the screen Back returns to from viewing history.
- **Parallel browser run** — the maintainer's run of these two checks
  together with other browser checks. That run is the proof this task
  requires.

## Q&A

- **Q:** Why does this task exist?
  **A:** Maintainers must trust that a busy quick add still locks and then
  unlocks the form, and that opening an older history entry still moves that
  list to the top and Back still returns home, when other browser checks run
  at the same time. Those two checks already pass sequentially and fail only
  under that load. A false red hides a real break, and a real red is easy to
  dismiss as load.

- **Q:** What must stay true for quick add?
  **A:** While the add is waiting, the form is busy and the add control
  cannot be used. When the wish is saved, the form is usable again and the
  new wish is on the list.

- **Q:** What must stay true for viewing history?
  **A:** Opening an older entry moves that list to the top. Back from
  history returns to the Mini App home. The screen has no console errors.

- **Q:** What counts as proof?
  **A:** The two named checks pass in a run where other browser checks run
  beside them. Passing them one after another does not close the task. A
  full suite that stops at 600 seconds is a different task (WISHENKA-285)
  and is not this proof.

- **Q:** What does not count as the fix?
  **A:** A longer fixed wait. The check must follow a condition it can see,
  or the request must stay held until the check releases it.

- **Q:** Which other work stays outside this task?
  **A:** WISHENKA-357 and WISHENKA-285. Also any addition of the substring
  `receipt` to `wishenka/web/static/app.js`.

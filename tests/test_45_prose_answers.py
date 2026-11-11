# tests/test_45_prose_answers.py
from conftest import make_fact
from kb.compose import HOURS_NOTE
from kb.types import ClaimType
from scoring import score_item

def _item(items, i): return next(it for it in items if it["id"] == i)
def _score(ks, it): return score_item(it, ks.answer(it["question"], it.get("as_of")))["score"]
CONTACT = "https://www.dupaco.com/contact"
CEDAR_RAPIDS = "https://www.dupaco.com/newsroom/dupaco-celebrates-completion-of-newest-learning-lab"  # dup-066's article

def test_general_lobby_hours_list_every_schedule(ks_full, public_items):
    a = ks_full.answer("What are Dupaco's general lobby hours?")
    lines = a.text.splitlines()
    assert [l.split(":")[0] for l in lines[:-1]] == [
        "Lobby hours at the Cedar Falls, Grimes and Waukee branches",
        "Lobby hours at the East Washington (Madison) and Mineral Point Road (Madison) branches",
        "Lobby hours at the Cedar Rapids branch", "Lobby hours at the Platteville branch"]
    assert lines[-1] == HOURS_NOTE and CONTACT in [s.url for s in a.sources]
    assert _score(ks_full, _item(public_items, "dup-064")) == _score(ks_full, _item(public_items, "dup-065")) == 1.0
    for q in ("What are the lobby hours at Dupaco branches?", "What time do Dupaco branches open?", "Lobby hours?"):
        assert ks_full.answer(q).text == a.text, q  # rewordings in one consistency group print the same schedules

def test_drive_up_hours(ks_full, public_items):
    a = ks_full.answer("What are the drive-up hours?")
    assert a.text.startswith("Drive-up hours at the Cedar Falls, Grimes and Waukee branches: Monday-Friday 8 a.m.")
    assert _score(ks_full, _item(public_items, "dup-066")) == 1.0  # the Cedar Rapids article is a source
    assert [l.split(":")[0] for l in a.text.splitlines()[1:-1]] == [  # two two-branch lines: the newer article first
        "Drive-up hours at the East Washington (Madison) and Mineral Point Road (Madison) branches",
        "Drive-up hours at the Cedar Rapids and Platteville branches"]
    assert {CEDAR_RAPIDS, CONTACT} <= {s.url for s in a.sources}

def test_same_lobby_hours_question(ks_full, public_items):
    a = ks_full.answer("Do all Dupaco branches keep the same lobby hours?")
    assert a.text.startswith("No. Hours vary by branch.") and "12:30" in a.text and "noon" in a.text
    assert _score(ks_full, _item(public_items, "dup-104")) == 1.0

def test_saturday_lobby_hours(ks_full):
    lines = ks_full.answer("What are Dupaco's Saturday lobby hours?").text.splitlines()
    assert all("Saturday" in l for l in lines[:-1]) and lines[-1] == HOURS_NOTE
    assert any("12:30" in l for l in lines) and any("noon" in l for l in lines) and any("Closed" in l for l in lines)

def test_named_branch_hours(ks_full):
    assert ks_full.answer("What are the lobby hours at the Platteville branch?").text == (  # page order: alphabetical would put Friday first
        "Lobby hours at the Platteville branch: Monday-Thursday 8:30 a.m.–5 p.m.; Friday 8:30 a.m.–5:30 p.m.; "
        "Saturday 9 a.m.–noon; Sunday Closed.")
    t = ks_full.answer("When does the drive-up at the Mineral Point Road branch close on Friday?").text
    assert "Mineral Point Road (Madison)" in t and "9 a.m." in t and "5 p.m." in t and HOURS_NOTE not in t
    for q in ("What are the lobby hours at the East Washington Avenue branch?", "What are the lobby hours at the East Washington Ave branch?"):
        assert ks_full.answer(q).text.startswith("Lobby hours at the East Washington (Madison) branch:"), q  # street words the stored name lacks

def test_named_branch_without_hours_refuses(ks_full, public_items):  # (pin)
    assert _score(ks_full, _item(public_items, "dup-102")) == 1.0
    for q in ("What are the lobby hours at the Hy-Vee branch?", "What are the drive-up hours at the Asbury branch?",
              "What are the lobby hours at the Dubuque branch?"):
        a = ks_full.answer(q)
        assert a.confident is False and not any(ch.isdigit() for ch in a.text), q

def test_lobby_questions_never_answer_reply_hours(ks_full):  # (pin)
    assert "Monday–Friday, 8:30 a.m.–5:30 p.m." not in ks_full.answer("What are the lobby hours?").text
    reply = ks_full.answer("When will Dupaco reply to a message I send through the contact form?").text
    assert "8:30" in reply and "5:30" in reply

def test_bare_branch_names_answer_that_branch_or_refuse(ks_full):  # on the Task 11 tree these answer with every branch's lines
    for q in ("What are the drive-up hours in Galena?", "What are the lobby hours in Dubuque?", "Lobby hours at Key West?"):
        a = ks_full.answer(q)
        assert a.confident is False and not any(ch.isdigit() for ch in a.text), q  # no hours facts for these branches
    assert ks_full.answer("What are the Platteville lobby hours?").text == ks_full.answer("What are the lobby hours at the Platteville branch?").text
    assert ks_full.answer("What time does the drive-up in Platteville close?").text.startswith("Drive-up hours at the Platteville branch:")
    assert ks_full.answer("What are the hours at Dupaco in Waukee?").text.startswith("Lobby hours at the Waukee branch:")

def test_hours_answers_carry_no_dates(ks_full):  # User decision 3
    a = ks_full.answer("What are Dupaco's general lobby hours?")
    assert ks_full.answer("What are Dupaco's general lobby hours?", "2026-06-30").text == a.text and not a.text.startswith("As of")
    assert not ks_full.answer("What are the lobby hours at the Platteville branch?", "2026-06-30").text.startswith("As of")

def test_other_hours_questions_refuse(ks_full):  # Task 11 review: on the Task 11 tree these print a confident all-branches list
    from scoring import _numbers
    for q in ("What are your holiday hours?", "What are Dupaco's hours on Christmas?", "What are the ATM hours?",
              "Are ATMs available 24 hours?", "What are the safe deposit box hours?", "What are Dupaco's customer service hours?",
              "What are the Member Service Center hours?", "What are the night deposit hours?", "What are the coin machine hours?",
              "What are the summer hours?", "What are the lobby hours at the corporate headquarters?",
              "What were the lobby hours before the remodel?"):
        a = ks_full.answer(q)
        assert a.confident is False and not _numbers(a.text) - _numbers(q), q

def _refuse_digit_free(ks, questions):
    for q in questions:
        a = ks.answer(q)
        assert a.confident is False and not any(ch.isdigit() for ch in a.text), (q, a.text)

# Task 12 review C1: "lobbies" made these hours questions, which printed every branch's lines (base refused them); a
# holiday or the weather is no branch schedule
def test_holiday_and_weather_hours_refuse(ks_full):
    _refuse_digit_free(ks_full, (
        "Are lobbies open on Memorial Day?", "Are Dupaco lobbies closed on Labor Day?", "Are lobbies open on July 4?",
        "Are lobbies open on the Fourth of July?", "Is the lobby open on July 4th?", "Is the lobby open on the 4th of July?",
        "Are the lobbies open on Independence Day?", "Are lobbies open on New Year's Day?", "Do lobbies close early on New Year's Eve?",
        "Are Dupaco's lobbies open on Veterans Day?", "Is the drive-thru open on Veterans Day?", "What are the lobby hours on Juneteenth?",
        "What are the hours on Presidents Day?", "Is the lobby open on Martin Luther King Day?", "Is the lobby open on MLK Day?",
        "Are the lobbies open on Easter Sunday?", "Are lobbies open on Good Friday?", "Are lobbies open on Black Friday?",
        "Is the drive-up open on Columbus Day?", "Are the lobbies closed due to weather?",
        "Are Dupaco lobbies closed today because of the snowstorm?", "Is the lobby closed for snow?", "Are lobbies closed during the storm?",
        "Is the drive-up open during a blizzard?"))

# Task 12 review I1: synonyms of the brief's refusal categories; "online" alone still asks the lobby hours
def test_other_hours_synonyms_refuse(ks_full):
    _refuse_digit_free(ks_full, (
        "What are the safety deposit box hours?", "What are your customer support hours?", "What are the customer care hours?",
        "What are the main office hours?", "What are the night depository hours?", "What are the Member Center hours?",
        "What are the support center hours?", "What are the live video teller hours?", "What are the after-hours drop box hours?",
        "What are the online banking hours?", "What are the mobile banking hours?", "What are the ITM hours?",
        "What are the hours for notary services?"))
    assert ks_full.answer("Where can I find the lobby hours online?").text == ks_full.answer("What are the lobby hours?").text

# Task 12 review I2: the opening wordings answer the lobby schedules, as dup-064 and dup-065 do, and a bare branch name
# in a where question answers that branch's address (a dup-068 rewording)
def test_opening_wordings_answer_the_schedules(ks_full):
    general = ks_full.answer("What are Dupaco's general lobby hours?").text
    for q in ("When are Dupaco branches open?", "When are your branches open?", "When are you open?", "When does Dupaco open?",
              "When can I come in?"):
        assert ks_full.answer(q).text == general, q
    for q in ("Do all Dupaco branches open and close at the same time?", "Are all Dupaco locations open at the same times?"):
        assert ks_full.answer(q).text.startswith("No. Hours vary by branch."), q
    assert ks_full.answer("Where is Dupaco in Galena?").text == ks_full.answer("What is the address of the Galena Branch?").text

# Task 12 review M2: two bare branch names print every schedule (as at base), never the first name's lines alone
def test_two_bare_branch_names_print_every_schedule(ks_full):
    assert ks_full.answer("What are the lobby hours in Grimes and Waukee?").text == ks_full.answer("What are the lobby hours?").text
    t = ks_full.answer("Are the Cedar Rapids and Waukee lobby hours the same?").text
    assert t.startswith("No. Hours vary by branch.") and "Platteville" in t

# M2 follow-up (Review Focus 1): a branch and its city ("the Hy-Vee in Dubuque") name one branch, the first written, so
# a branch without hours refuses instead of printing every schedule; only names a list word joins name several
def test_a_branch_and_its_city_name_one_branch(ks_full):
    _refuse_digit_free(ks_full, ("What are the drive-up hours at the Hy-Vee in Dubuque?", "What are the lobby hours at Key West in Dubuque?",
                                 "What are the drive-up hours at Hy-Vee, Dubuque?", "What are the lobby hours at Hillcrest Rd., Dubuque?"))
    for q in ("What are the lobby hours at East Washington in Madison?", "What are the lobby hours at East Washington, Madison?"):
        t = ks_full.answer(q).text  # a comma alone joins no list: the site itself writes "street, city"
        assert t.startswith("Lobby hours at the East Washington (Madison) branch:") and HOURS_NOTE not in t, q

# Task 12 review M4: the Carroll, Dyersville and Manchester branches, which no hours fact names, refuse
def test_more_bare_branch_names_refuse(ks_full):
    _refuse_digit_free(ks_full, ("What are the lobby hours in Dyersville?", "What are the lobby hours in Carroll?",
                                 "What are the drive-up hours in Manchester?"))

# Task 11 review: a phone question with a lobby or drive-up cue asks the phone number, so W5 refuses a branch known from
# an hours article alone; Phase 2 carry: "lobby phone number for Mars" answered the contact form's reply hours
def test_phone_questions_with_a_lobby_cue_never_print_hours(ks_full):
    phone = ks_full.answer("What is the phone number for the Platteville branch lobby?")
    assert phone.confident and "(608) 348-4499" in phone.text and "hours" not in phone.text  # A11b: article phone
    for q in ("What number do I call for the Waukee branch lobby?",):
        a = ks_full.answer(q)
        assert a.confident is False and not any(ch.isdigit() for ch in a.text), q
    assert "8:30" not in ks_full.answer("lobby phone number for Mars").text

# Task 5 review: a yes/no hours question naming a branch lost the branch and answered every branch's Saturday line
def test_a_yes_no_hours_question_answers_the_branch_it_names(ks_full):
    assert ks_full.answer("Are the Cedar Rapids lobby hours 9 to 5 on Saturday?").text == (
        "Lobby hours at the Cedar Rapids branch: Saturday 8:30 a.m.-12:30 p.m.")

# ruling: street words alone name no branch (the street-word rule would otherwise match every stored name)
def test_street_words_alone_name_no_branch(ks_full):
    for q in ("What are the lobby hours at the Main Street branch?", "What are the drive-up hours at the Avenue branch?"):
        a = ks_full.answer(q)
        assert a.confident is False and not any(ch.isdigit() for ch in a.text), q
    assert ks_full.answer("What is the address of the Main Street branch?").confident is False  # base: Peosta and Sycamore St.

def _hours(branch, day, value, row, published):  # a prose lobby-hours fact as kb.extract_prose reads one
    return make_fact("branch", "lobby_hours", value, extractor="prose", claim=ClaimType.ASSERTION, unit="text",
                     published=published, row=row, branch_name=branch, day=day)

def test_schedules_share_equal_lines_in_page_order():
    from kb.compose_prose import branch_display, schedules
    assert (branch_display("east washington, madison"), branch_display("platteville")) == ("East Washington (Madison)", "Platteville")
    assert branch_display("oldenburg ln., galena") == "Oldenburg Ln (Galena)"  # no ". " inside a label: the lint splits there
    facts = [_hours("b", "sunday", "Closed", 9, "2022-01-01"), _hours("b", "monday-friday", "9 a.m.–5 p.m.", 5, "2022-01-01"),
             _hours("a", "monday-friday", "9 a.m.-5 p.m.", 7, "2023-01-01"), _hours("a", "sunday", "closed", 8, "2023-01-01"),
             _hours("c", "monday-friday", "8 a.m.–6 p.m.", 1, "2024-01-01")]
    assert schedules(facts) == [(("A", "B"), (("monday-friday", "9 a.m.-5 p.m."), ("sunday", "closed"))),  # a's newer surface
                                (("C",), (("monday-friday", "8 a.m.–6 p.m."),))]


# Phase 3 Task 13: closures, branch status at a date, alternatives
def test_hy_vee_close_date_and_status(ks_full, public_items):
    assert ks_full.answer("When does the Hy-Vee branch close?").text == "The Hy-Vee branch closed on March 31, 2026."
    assert ks_full.answer("Is the Hy-Vee branch still open today (October 2026)?").text == "No. The Hy-Vee branch closed on March 31, 2026."
    assert _score(ks_full, _item(public_items, "dup-074")) == _score(ks_full, _item(public_items, "dup-075")) == 1.0

def test_closure_status_against_as_of(ks_full):
    assert ks_full.answer("When does the Hy-Vee branch close?", "2026-03-01").text == "The Hy-Vee branch is scheduled to close on March 31, 2026."
    assert ks_full.answer("When does the Hy-Vee branch close?", "2026-05-31").text == "The Hy-Vee branch closed on March 31, 2026."
    assert ks_full.answer("When did the Asbury branch close?").text == "The Asbury branch closed on Oct. 1, 2024."

def test_closure_unknown_before_publication(ks_full):  # (pin)
    a = ks_full.answer("When does the Hy-Vee branch close?", "2025-01-01")
    assert a.confident is False and not any(ch.isdigit() for ch in a.text)

def test_alternatives(ks_full, public_items):
    assert ks_full.answer("Where can Hy-Vee branch members go for full-service banking?").text == (
        "Members of the Hy-Vee branch can use Dupaco's full-service branches at Key West and Sycamore Street.")
    assert _score(ks_full, _item(public_items, "dup-076")) == 1.0

# Task 12 carry: a bare branch name binds in status and alternatives questions too
def test_bare_branch_names_answer_status_questions(ks_full):
    assert ks_full.answer("Is Hy-Vee still open?").text == "No. The Hy-Vee branch closed on March 31, 2026."
    assert ks_full.answer("When does Hy-Vee close?", "2026-03-01").text == "The Hy-Vee branch is scheduled to close on March 31, 2026."
    a = ks_full.answer("Which branch should Hy-Vee members use instead?", "2026-06-30")  # undated, as the status lines are
    assert a.text == "Members of the Hy-Vee branch can use Dupaco's full-service branches at Key West and Sycamore Street."
    for q in ("Is the Mullan Avenue branch still open?", "When does the Key West branch close?", "Where can Galena branch members go instead?"):
        a = ks_full.answer(q)
        assert a.confident is False and not any(ch.isdigit() for ch in a.text), q  # no closure or alternative names them

def test_status_questions_naming_no_branch(ks_full):  # review: on 2533337 the first four print both closures, confident
    for q in ("Is the branch open today?", "Are branches open on holidays?", "Is the branch open on Christmas Day?",
              "When does the branch close?"):
        a = ks_full.answer(q)
        assert a.confident is False and not any(ch.isdigit() for ch in a.text), q
    both = "The Asbury branch closed on Oct. 1, 2024.\nThe Hy-Vee branch closed on March 31, 2026."
    assert ks_full.answer("Which branches have closed?").text == ks_full.answer("Are any branches closing?").text == both  # (pin)
    assert ks_full.answer("Is the Hy-Vee branch open on Christmas?").text == "No. The Hy-Vee branch closed on March 31, 2026."  # (pin)

def test_the_asbury_road_branch_is_not_the_closed_asbury_branch(ks_full):  # 4730 Asbury Rd, Dubuque (/contact) is open
    for q in ("Is the Asbury Road branch still open?", "When did the Asbury Road branch close?",
              "Where can Asbury Road branch members go instead?", "What's the branch closing cost?"):
        a = ks_full.answer(q)
        assert a.confident is False and not any(ch.isdigit() for ch in a.text), q  # on 2533337 the Asbury closure answers
    from kb.tiers import branch_named
    madison = make_fact("branch", "lobby_hours", "9 a.m.–5 p.m.", branch_name="east washington, madison")
    asbury = _closure("asbury", "Oct. 1, 2024", "2024-10-01", "2024-06-06")
    assert branch_named([madison, asbury], "asbury road") == [] and branch_named([madison, asbury], "asbury") == [asbury]
    assert branch_named([madison, asbury], "east washington avenue") == [madison]  # (pin) a street part may lack the type

def test_a_closure_lists_no_branch_for_contact_questions(ks_full):  # test_21's Hy-Vee phone pin failed on the first cut
    for q in ("What is the phone number at the Hy-Vee branch?", "What is the address of the Asbury branch?",
              "What is the phone number for the Asbury branch?"):
        a = ks_full.answer(q)
        assert a.confident is False and not any(ch.isdigit() for ch in a.text), q

# ruling: the verdict answers "is it open?", so only a question with the word "open" about one branch gets one; "No." for
# "Is the Asbury branch closed?" would contradict its own line
def test_status_verdicts_only_answer_open_questions(ks_full):
    assert ks_full.answer("Is the Hy-Vee branch still open?", "2026-03-01").text == "Yes. The Hy-Vee branch is scheduled to close on March 31, 2026."
    assert ks_full.answer("Is the Asbury branch closed?").text == "The Asbury branch closed on Oct. 1, 2024."
    assert ks_full.answer("Has the Hy-Vee branch closed?", "2026-03-01").text == "The Hy-Vee branch is scheduled to close on March 31, 2026."

def _closure(branch, value, event, published, sid="05_2026-09-28_latest"):  # a closure fact as kb.extract_prose reads one
    return make_fact("branch", "closure_date", value, extractor="prose", claim=ClaimType.STATUS, unit="text", event=event,
                     published=published, snapshot_id=sid, branch_name=branch)

def test_status_lines_read_the_reference_date():
    from dataclasses import replace
    from conftest import single_plan
    from kb.compose_prose import render_status
    hy, asbury = _closure("hy-vee", "March 31, 2026", "2026-03-31", "2025-06-20"), _closure("asbury", "Oct. 1, 2024", "2024-10-01", "2024-06-06")
    plan = single_plan("status", hy, question="Is the Hy-Vee branch open?")
    assert render_status(replace(plan, as_of="2026-03-31")) == "Yes. The Hy-Vee branch is scheduled to close on March 31, 2026."  # the event day
    assert render_status(replace(plan, crawl_date="2026-04-01")) == "No. The Hy-Vee branch closed on March 31, 2026."
    assert render_status(replace(plan, as_of="2026-03-01", crawl_date="2026-09-28")).startswith("Yes.")  # as_of first
    assert render_status(plan) == "No. The Hy-Vee branch closed on March 31, 2026."  # no date on the plan: its crawl id's
    for q in ("When is the Hy-Vee branch open until?", "Do you know the date the Hy-Vee branch stops being open?", "Hy-Vee open?"):
        assert render_status(replace(plan, question=q)) == "The Hy-Vee branch closed on March 31, 2026.", q
    two = replace(plan, facts=(asbury, hy), question="Is the branch open today?")
    assert render_status(two) == "The Asbury branch closed on Oct. 1, 2024.\nThe Hy-Vee branch closed on March 31, 2026."
    old = make_fact("branch", "status", "Closing November 14, 2026", branch_name="hy-vee")  # no event date: the Phase 2 line
    assert render_status(single_plan("status", old, question="Is the Hy-Vee branch open?")) == "Hy-Vee Branch: Closing November 14, 2026."

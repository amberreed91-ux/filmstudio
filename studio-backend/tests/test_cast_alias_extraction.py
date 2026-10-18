from app.services.script_parser import ScriptParser


def test_all_six_brothers_including_single_letter_and_offscreen_cues():
    introductions = '\n'.join([
        'MALCOLM "MAK" COLE, 29, watches.',
        'PRESTON "PRETTY BOY" COLE, 25, waits.',
        'RASHAD "RASTA" COLE, 23, watches.',
        'DESMOND "SCAR" COLE, 21, waits.',
        'TERRENCE "T" COLE, 18, watches.',
        'KENDRICK "KINKY TAILE" COLE, 15, waits.',
    ])
    script = 'EXT. LOT - NIGHT\n' + introductions + '\nPRETTY\nHello.\nKINK\nHello.\nMAK\nCome here.\nT (O.S.)\nYes.\nRASTA (O.S.)\nComing.\nINT. CAR - NIGHT\nMAK\nGet in.\nT\nAll right.'
    scenes = ScriptParser().extract_structured_scenes(script)['scenes']
    assert len(scenes[0]['characters']) == 6
    assert scenes[1]['characters'] == ['MALCOLM "MAK" COLE', 'TERRENCE "T" COLE']


def test_single_letter_and_phone_cues():
    names = ScriptParser()._extract_simple_scene_characters('T\nHello.\nMONIQUE (PHONE)\nCome home.\nRASTA (O.S.)\nWait.')
    assert names == ['T', 'MONIQUE', 'RASTA']


def test_shared_nicknames_are_not_merged():
    text = 'INT. HOME - DAY\nJAMES "JIM" COLE, 30.\nJIMOTHY "JIM" COLE, 40.\nJIM\nHello.'
    names = ScriptParser().extract_structured_scenes(text)['scenes'][0]['characters']
    assert 'JIM' in names
    assert len(names) == 3


def test_whole_cast_includes_plain_names_silent_roles_and_shouted_phone_dialogue():
    text = '''A FILM
Written by
A Writer
INT. CLINIC - DAY
DEON HOLLIS, mid twenties, waits.
ARIELLE COLE, 9, watches silently.
MR. BELL, seventies, sits nearby.
DENISE
WHITAKER, elegant, watches.
DEON
Hello.
DENISE
Hello.
NURSE
Come inside.
MONIQUE (PHONE)
GET OUT!
CUT TO BLACK.
'''
    names, _ = ScriptParser().extract_cast(text)
    assert set(names) == {'DEON HOLLIS', 'ARIELLE COLE', 'MR. BELL', 'DENISE WHITAKER', 'NURSE', 'MONIQUE'}


def test_two_people_sharing_first_name_remain_distinct():
    names, _ = ScriptParser().extract_cast('INT. HOME - DAY\nJAMES COLE, 30, waits.\nJAMES REED, 40, waits.\nJAMES\nHello.')
    assert set(names) == {'JAMES COLE', 'JAMES REED', 'JAMES'}


def test_surname_cue_needs_introduction_context_not_just_shared_family_name():
    text = 'INT. HOME - DAY\nDEON HOLLIS, 25, waits.\nDEON\nHello.\nVINCENT HOLLIS approaches him.\nHOLLIS\nHello.'
    names, aliases = ScriptParser().extract_cast(text)
    assert set(names) == {'DEON HOLLIS', 'VINCENT HOLLIS'}
    assert aliases['HOLLIS'] == 'VINCENT HOLLIS'


def test_full_script_aliases_apply_to_later_scenes_without_introductions():
    scenes = ScriptParser().extract_structured_scenes('INT. HOME - DAY\nDEON HOLLIS, 25, waits.\nDEON\nHello.\nEXT. STREET - NIGHT\nDEON\nGoodbye.')['scenes']
    assert scenes[1]['characters'] == ['DEON HOLLIS']

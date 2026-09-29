"""The code net under WORD SALAD.

Measured: every Groq model misses pure corporate buzzwords, including the
120b, which is six times the size of the 20b -- so this is not fixed by
spending more on a model. It is a closed vocabulary of about forty words,
which is a set membership test, not a language problem.

The danger is the opposite direction. A false positive stamps WORD SALAD on
a real claim and skips checking it, so every test below that asserts False
is guarding something that must still reach the judge.
"""

from server.buzzwords import hits, is_word_salad


def test_it_catches_what_the_models_miss():
    # The three the 120b returned nothing for.
    assert is_word_salad("This product will revolutionize the market through cross functional synergy.")
    assert is_word_salad("We're going to leverage our core competencies to unlock synergistic value.")
    assert is_word_salad("This is a genuine step change in velocity for the org.")


def test_one_buzzword_is_not_enough():
    # People say "leverage" in real sentences. Two distinct ones are required.
    assert not is_word_salad("We should leverage that.")
    assert not is_word_salad("It is a robust approach.")


def test_a_number_means_it_is_checkable():
    # Buzzwords wrapped around a measurable assertion is still an assertion.
    assert not is_word_salad("We cut latency by 40 percent through streamlining.")
    assert not is_word_salad("Our scalable ecosystem serves 10 million stakeholders.")


def test_a_named_thing_means_it_is_checkable():
    # A claim about something with a name must reach the judge however it
    # is dressed up, or a real check is lost.
    assert not is_word_salad("Snowflake is revolutionising the data ecosystem.")
    assert not is_word_salad("Amazon Web Services is a transformative paradigm.")


def test_ordinary_speech_is_left_alone():
    assert not is_word_salad("My name is Shray.")
    assert not is_word_salad("Yeah totally, anyway where were we.")
    assert not is_word_salad("")
    assert not is_word_salad("   ")


def test_a_phrase_counts_once_not_as_its_words():
    # "core competencies" is one idea. If it also counted "competenc" and
    # some stray word, a single phrase would trip the threshold of two.
    assert hits("our core competencies").count("core competenc") == 1
    assert not is_word_salad("Our core competencies matter.")

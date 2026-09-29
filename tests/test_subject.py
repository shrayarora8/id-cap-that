"""What a claim is *about*, which decides which Wikipedia article we read.

This is not cosmetic. Getting it wrong does not degrade the answer, it
replaces it: "Dancing on My Own is by Callum Scott" once truncated to
"Dancing", fetched the article about dance as an art form, and the judge
correctly said it could not settle the claim from passages about body
movement -- so a claim with a clear, checkable answer came back unresolved,
after paying for a judge call and a search it should never have needed.
"""

from server.retrieval import _subject_of


def test_a_plain_subject_is_the_leading_proper_nouns():
    assert _subject_of("Mount Everest is 8,848 metres tall.") == "Mount Everest"
    assert _subject_of("Spotify has over 600 million users.") == "Spotify"
    assert _subject_of("Rust was created at Mozilla.") == "Rust"


def test_a_name_may_contain_lowercase_connectors():
    # The bug: these all stopped at the first lowercase word.
    assert _subject_of("Dancing on My Own was performed by Callum Scott.") == "Dancing on My Own"
    assert _subject_of("Bank of America is in Charlotte.") == "Bank of America"
    assert _subject_of("University of Oxford was founded in 1096.") == "University of Oxford"


def test_a_connector_run_reaches_the_next_capital():
    # "of the Rings" -- two connectors before the name resumes, and "the" is
    # a stop word in its own right, which is what broke the first fix.
    assert _subject_of("The Lord of the Rings was written by Tolkien.") == "Lord of the Rings"
    assert _subject_of("Pirates of the Caribbean came out in 2003.") == "Pirates of the Caribbean"


def test_a_leading_article_is_not_part_of_the_subject():
    assert _subject_of("The Nile is the longest river.") == "Nile"
    assert _subject_of("The Burj Khalifa is 828 metres tall.") == "Burj Khalifa"


def test_a_name_never_ends_on_a_connector():
    # "plays for Al Nassr" must not drag "for" onto the end of the subject.
    assert _subject_of("Cristiano Ronaldo plays for Al Nassr.") == "Cristiano Ronaldo"
    assert _subject_of("Notion costs eight dollars a seat.") == "Notion"


def test_a_claim_with_no_proper_noun_falls_back_to_the_text():
    assert _subject_of("water boils at 100 degrees") == "water boils at 100 degrees"

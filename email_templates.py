"""
Email copy for the "Excitement is Building" outreach -- the initial blast to
past Discovery! volunteers/TAs, plus its automated follow-ups. Kept separate
from app.py so the wording can be revised without touching route logic, and
reused identically by the one-off test send and the eventual full blast.
"""

from config import PROGRAM_NAME, DISCOVERY_URL

EXCITEMENT_BLAST_SUBJECT = f"{PROGRAM_NAME} Excitement is Growing"


def _connect_blocks(connect_url):
    """The optional personal "reach out to me" paragraph used by the
    blast emails. Returns (html, text); both empty when there is no link."""
    connect_html = ""
    connect_text = ""
    if connect_url:
        connect_html = f"""
        <p>Want me to personally follow up with you? <a href="{connect_url}">Click here</a> and
        let me know the best way to reach you &mdash; email or a call &mdash; and I'll get to you
        as soon as I possibly can. So many of you have already reached out, and every single one
        of you matters to me, even though I'm just one guy trying to keep up!</p>
        """
        connect_text = (
            f"Want me to personally follow up with you? Click here and let me know the best way "
            f"to reach you -- email or a call -- and I'll get to you as soon as I possibly can. So "
            f"many of you have already reached out, and every single one of you matters to me, "
            f"even though I'm just one guy trying to keep up!\n{connect_url}\n\n"
        )
    return connect_html, connect_text


def excitement_blast_content(first_name, connect_url=None):
    """Returns (html_content, text_content) for the initial blast email,
    personalized with the contact's first name. connect_url, if given, is
    that contact's personal link to the "reach out to me" page -- lets
    someone ask Kent to personally follow up (by email or phone) without
    emailing him directly, so replies don't just pile up in his inbox."""
    greeting = first_name.strip() if first_name and first_name.strip() else "Friend"

    connect_html, connect_text = _connect_blocks(connect_url)

    html_content = f"""
        <p style="font-size:1.6em; font-weight:bold; margin-bottom:20px;">{PROGRAM_NAME} Excitement is Growing!!!</p>
        <p>Dear {greeting},</p>
        <p>Please forgive the intrusion &mdash; this is Kent Hafemann, and you're receiving this
        email because you're someone I've known or worked with over the years, whether through
        business, family, friend, or just life.</p>
        <p>Some of you are aware of Discovery!, a powerful and life-changing
        personal-growth and relationship training that Pamela and I have been involved with
        since 1996. Unfortunately, the program closed in 2020 because of COVID-19. Yet many have
        expressed a strong desire to reopen the program. Nothing is official yet, but we're
        working hard to make that happen.</p>
        <p>Our hope is in the next few months we will be meeting with those who attended or
        volunteered in the training. If you were a Discovery! volunteer, or if you are interested
        to know more about this program, we would love to hear from you.</p>
        <p><span style="font-size:1.25em; font-weight:bold; color:#1f6fb2;">Please open the link
        below and complete a brief contact form so that you will be among the first to know when
        a meeting date is set, or additional information is available.</span></p>
        <p><a href="{DISCOVERY_URL}">{DISCOVERY_URL}</a></p>
        {connect_html}
        <p>Please share this link and help us get the word out.</p>
        <p>Thanks so much. Indeed, the excitement is building!!!</p>
        <p>Your support and giving hearts are much appreciated.</p>
        <p>We look forward to seeing you soon.</p>
        <p>Blessings on you,<br>Kent Hafemann</p>
    """

    text_content = f"""DALLAS DISCOVERY EXCITEMENT IS GROWING!!!

Dear {greeting},

Please forgive the intrusion -- this is Kent Hafemann, and you're receiving this email because you're someone I've known or worked with over the years, whether through business, family, friend, or just life.

Some of you are aware of Discovery!, a powerful and life-changing personal-growth and relationship training that Pamela and I have been involved with since 1996. Unfortunately, the program closed in 2020 because of COVID-19. Yet many have expressed a strong desire to reopen the program. Nothing is official yet, but we're working hard to make that happen.

Our hope is in the next few months we will be meeting with those who attended or volunteered in the training. If you were a Discovery! volunteer, or if you are interested to know more about this program, we would love to hear from you.

Please open the link below and complete a brief contact form so that you will be among the first to know when a meeting date is set, or additional information is available.

{DISCOVERY_URL}

{connect_text}Please share this link and help us get the word out.

Thanks so much. Indeed, the excitement is building!!!

Your support and giving hearts are much appreciated.

We look forward to seeing you soon.

Blessings on you,
Kent Hafemann
"""

    return html_content, text_content


BLAST2_SUBJECT = f"{PROGRAM_NAME} Excitement is Growing"


def blast2_cover_content(first_name):
    """Returns (html_content, text_content) for Email Blast #2 -- the cover
    letter for the Discovery! contact database (people who already know
    the program, so no introduction of who Kent is). Deliberately has no
    personal "reach out to me" paragraph. NOT sent automatically by anything."""
    greeting = first_name.strip() if first_name and first_name.strip() else "Friend"

    html_content = f"""
        <p>Dear {greeting},</p>
        <p>As you know, the Discovery! training closed in 2020 because of COVID-19. Yet
        many have expressed a strong desire to reopen the program. Nothing is official yet, but
        we're working hard to make that happen.</p>
        <p>Our hope is in the next few months we will be meeting with those who attended or
        volunteered in the training. If you were a Discovery! volunteer, or if you are interested
        to know more about this program, we would love to hear from you.</p>
        <p><span style="font-size:1.25em; font-weight:bold; color:#1f6fb2;">Please open the link
        below and complete a brief contact form so that you will be among the first to know when
        a meeting date is set, or additional information is available.</span></p>
        <p><a href="{DISCOVERY_URL}">{DISCOVERY_URL}</a></p>
        <p>Please share this link and help us get the word out.</p>
        <p>Thanks so much. Indeed, the excitement is building!!!</p>
        <p>Your support and giving hearts are much appreciated.</p>
        <p>We look forward to seeing you soon.</p>
        <p>Blessings on you,<br>Kent Hafemann</p>
    """

    text_content = f"""Dear {greeting},

As you know, the Discovery! training closed in 2020 because of COVID-19. Yet many have expressed a strong desire to reopen the program. Nothing is official yet, but we're working hard to make that happen.

Our hope is in the next few months we will be meeting with those who attended or volunteered in the training. If you were a Discovery! volunteer, or if you are interested to know more about this program, we would love to hear from you.

Please open the link below and complete a brief contact form so that you will be among the first to know when a meeting date is set, or additional information is available.

{DISCOVERY_URL}

Please share this link and help us get the word out.

Thanks so much. Indeed, the excitement is building!!!

Your support and giving hearts are much appreciated.

We look forward to seeing you soon.

Blessings on you,
Kent Hafemann
"""

    return html_content, text_content


CONNECT_REQUEST_SUBJECT = "I got your message -- thank you"


def connect_request_confirmation_content(first_name, method):
    """Returns (html_content, text_content) for the auto-reply sent right
    after someone submits the "please reach out to me personally" request
    on the /connect/<token> page -- a personal note from Kent explaining
    that many people have reached out, that they matter to him, and that
    he'll get to them as soon as he can (he's one person, not a team)."""
    greeting = first_name.strip() if first_name and first_name.strip() else "Friend"
    how = "give you a call" if method == "Phone" else "email you personally"

    html_content = f"""
        <p>Dear {greeting},</p>
        <p>Thank you so much for letting me know you'd like me to {how} &mdash; I got your
        message, and I wanted to write back right away so you know it didn't just disappear into
        the void.</p>
        <p>So many of you have reached out already, and I want you to know that every single one
        of you matters to me. I'm doing my best to personally get back to each person, but I'm
        just one guy right now, so it may take me a little time. Please bear with me &mdash; I
        promise I will get to you as soon as I possibly can.</p>
        <p>Thank you again for your patience, and for being part of this with me.</p>
        <p>Blessings on you,<br>Kent Hafemann</p>
    """

    text_content = (
        f"Dear {greeting},\n\n"
        f"Thank you so much for letting me know you'd like me to {how} -- I got your message, "
        "and I wanted to write back right away so you know it didn't just disappear into the void.\n\n"
        "So many of you have reached out already, and I want you to know that every single one of "
        "you matters to me. I'm doing my best to personally get back to each person, but I'm just "
        "one guy right now, so it may take me a little time. Please bear with me -- I promise I "
        "will get to you as soon as I possibly can.\n\n"
        "Thank you again for your patience, and for being part of this with me.\n\n"
        "Blessings on you,\nKent Hafemann"
    )

    return html_content, text_content


INTERESTED_PARTY_WELCOME_SUBJECT = f"Thank you for your interest in {PROGRAM_NAME}"


def interested_party_welcome_content(first_name, connect_url=None):
    """Returns (html_content, text_content) for the welcome email sent when
    someone selects "Interested Party" (rather than a past volunteer role)
    on the /discovery short form -- thanks them for their interest and
    shares Kent and Pamela's own story. connect_url, if given, is that
    contact's personal link to the "reach out to me" page, so they can ask
    for a personal call that the Hub records."""
    greeting = first_name.strip() if first_name and first_name.strip() else "Friend"

    paras = [
        "Thank you for your interest in Sojourn. I\u2019d like to share why this training has meant so much to Pamela and me.",
        "In 1996, our marriage was struggling. We had three children and had tried counseling, pastoral guidance, and just about everything we could think of. Yet our marriage seemed to be slipping through our fingers.",
        "Then a close friend invited us to attend a three-day experiential training. Pamela attended first.",
        "I\u2019ll never forget the phone call I received from her while I was at work. That conversation became a turning point in our marriage and the beginning of a remarkable journey.",
        "Through the training, we began to understand how our past experiences influenced our attitudes, behaviors, and relationships. We learned practical ways to communicate, navigate conflict, take personal responsibility, and extend forgiveness and grace to ourselves and each other.",
        "It wasn\u2019t a magical fix. The real change came as we began putting what we\u2019d learned into practice.",
        "Since then, we\u2019ve participated in and helped facilitate numerous personal-growth and relationship programs. We continue to believe deeply in the value of this experience.",
        "Unlike most trainings, this training invites participants into an immersive experience, personal reflection, and meaningful conversations. It\u2019s an invitation to become curious about yourself, explore new perspectives, and discover possibilities for your life and relationships that you may not have considered before.",
        "Our next weekend for couples, The Art of Us, is February 12\u201314, 2027. If you would like to know more, we would be glad to tell you.",
        "If you have questions or would like to speak with one of our experienced volunteers, simply reply to this email. We\u2019d love to hear from you.",
    ]
    import html as _html
    body_html = "".join(f"<p>{_html.escape(p, quote=False)}</p>" for p in paras)
    body_text = "\n\n".join(paras)
    if connect_url:
        body_html += f'<p>Prefer a call? <a href="{connect_url}">Click here</a> and one of us will reach out to you.</p>'
        body_text += f"\n\nPrefer a call? Use the link below and one of us will reach out to you.\n{connect_url}"

    html_content = f"""
        <p>Dear {greeting},</p>
        {body_html}
        <p>Warm regards,<br>Kent Hafemann</p>
    """
    text_content = f"Dear {greeting},\n\n{body_text}\n\nWarm regards,\nKent Hafemann\n"
    return html_content, text_content


LONGFORM_FOLLOWUP_SUBJECT = "Thank you! One more quick step for our volunteer teams"


def longform_followup_content(first_name, longform_url):
    """Returns (html_content, text_content) for the short thank-you email
    that carries someone's personal profile link -- sent right after they
    check "Volunteer" on the discovery short form, and reusable any time
    that link needs to be sent or re-sent by hand."""
    html_content = f"""
        <p>Hi {first_name},</p>
        <p>Thank you so much for adding your name &mdash; it means a lot to know you're
        interested in helping bring this training back to life.</p>
        <p>As promised, here's a short follow-up form with a bit more information that
        will help us organize our volunteer teams:</p>
        <p><a href="{longform_url}">{longform_url}</a></p>
        <p>No rush at all &mdash; fill it out whenever you get a chance. Your answers save as you go, so you can close the page and pick up right where you left off by opening the same link again.</p>
        <p>Thanks again for your support and your giving heart.</p>
        <p>Blessings,<br>Kent Hafemann</p>
    """
    text_content = (
        f"Hi {first_name},\n\n"
        "Thank you so much for adding your name -- it means a lot to know you're "
        "interested in helping bring this training back to life.\n\n"
        "As promised, here's a short follow-up form with a bit more information that "
        f"will help us organize our volunteer teams:\n{longform_url}\n\n"
        "No rush at all -- fill it out whenever you get a chance. Your answers save as you go, so you can close the page and pick up right where you left off by opening the same link again.\n\n"
        "Thanks again for your support and your giving heart.\n\nBlessings,\nKent Hafemann"
    )
    return html_content, text_content


LONGFORM_THANKYOU_SUBJECT = "Thank you!"


def longform_thankyou_content(first_name, connect_url, plan_url, share_url=None):
    """Returns (html_content, text_content) for the thank-you email sent
    when someone clicks Submit on the public profile (complete-profile)
    -- not every autosave, just that final submit. Offers two separate
    opt-ins: plan_url is a button that sends them the (much longer)
    Preliminary Discovery! Plan email (see preliminary_plan_content below)
    -- it's only sent if they click through, not automatically. connect_url
    is their personal /connect link so they can ask Kent to follow up
    directly if they'd like, without needing to reply to this email."""
    greeting = first_name.strip() if first_name and first_name.strip() else "Friend"

    share_html = ""
    share_text = ""
    if share_url:
        share_html = (
            "<p><strong>One more thing:</strong> you may have heard we are inviting former trainees &amp; volunteers to "
            "share how the program has touched their lives, and the lives of their family and friends. We'd love to hear "
            "about your experience with the training. It only takes a couple of minutes. You can speak it, type it, or "
            "record yourself. Your story may help someone else take their first step.</p>"
            f'<p style="margin:22px 0"><a href="{share_url}" style="display:inline-block; background:#0c4561; color:#ffffff; '
            'text-decoration:none; font-weight:700; padding:14px 28px; border-radius:8px;">Share your experience</a></p>'
            "<p>Nothing is published without your approval. We'll show you the final version first, and we'll add "
            "testimonials to the website once enough of you have responded.</p>"
        )
        share_text = (
            "One more thing: you may have heard we are inviting former trainees & volunteers to share how the program "
            "has touched their lives, and the lives of their family and friends. We'd love to hear about your experience "
            "with the training. It only takes a couple of minutes. You can speak it, type it, or record yourself. Your "
            "story may help someone else take their first step.\n\n"
            f"Share your experience: {share_url}\n\n"
            "Nothing is published without your approval. We'll show you the final version first, and we'll add "
            "testimonials to the website once enough of you have responded.\n\n"
        )

    html_content = f"""
        <p>Dear {greeting},</p>
        <p>Thank you for taking the time to complete the &ldquo;Additional Information&rdquo;
        form &mdash; we appreciate your effort and your energy.</p>
        <p>What you shared helps us as we work to bring Discovery! back to life, and it tells me
        you still care about what this program stands for.</p>
        <p>I've put together a preliminary outline of where things stand, including our mission
        and goals, the tasks involved with getting this training running again, and where there
        might be a place for you.</p>
        <p>In short&hellip; we need an army of serious volunteers willing to dig deep and take on
        responsibility. If you wish, we'll send you the plan outline.</p>
        <p><a href="{plan_url}" style="display:inline-block; background:#1f6fb2; color:#ffffff;
        text-decoration:none; font-weight:700; padding:12px 22px; border-radius:8px;">Send me the
        Preliminary Discovery! Plan</a></p>
        {share_html}
        <p>Thanks again for all that you have done in years past, and for perhaps all that you
        will be doing for Discovery! in the future.</p>
        <p>If you'd like for me to personally reach out to you &mdash; just
        <a href="{connect_url}">click here</a> and I'll get to you as soon as I can.</p>
        <p>Thank you again for your time, your heart, and your support.</p>
        <p>Blessings on you,<br>Kent Hafemann</p>
    """

    text_content = (
        f"Dear {greeting},\n\n"
        "Thank you for taking the time to complete the \"Additional Information\" form -- we "
        "appreciate your effort and your energy.\n\n"
        "What you shared helps us as we work to bring Discovery! back to life, and it tells me "
        "you still care about what this program stands for.\n\n"
        "I've put together a preliminary outline of where things stand, including our mission "
        "and goals, the tasks involved with getting this training running again, and where "
        "there might be a place for you.\n\n"
        "In short... we need an army of serious volunteers willing to dig deep and take on "
        "responsibility. If you wish, we'll send you the plan outline:\n"
        f"{plan_url}\n\n"
        f"{share_text}"
        "Thanks again for all that you have done in years past, and for perhaps all that you "
        "will be doing for Discovery! in the future.\n\n"
        "If you'd like for me to personally reach out to you -- just click the link below and "
        f"I'll get to you as soon as I can.\n{connect_url}\n\n"
        "Thank you again for your time, your heart, and your support.\n\n"
        "Blessings on you,\nKent Hafemann"
    )
    return html_content, text_content


PRELIMINARY_PLAN_SUBJECT = "Preliminary business plan for Discovery!"


def preliminary_plan_content(first_name):
    """Returns (html_content, text_content) for the Preliminary Discovery!
    Plan email -- sent only when staff click "Send business plan" on a contact,
    or someone clicks the "Send me the Preliminary Discovery! Plan" button in the
    profile thank-you email, never automatically. Lays out Kent's mission and
    goals for relaunching Discovery! and the volunteer help still needed."""
    greeting = first_name.strip() if first_name and first_name.strip() else "Friend"

    html_content = f"""
        <p>Dear {greeting},</p>
        <p>Thanks for your continued interest in the {PROGRAM_NAME} launch.</p>
        <p>So, what are the goals and mission for {PROGRAM_NAME}? Perhaps you may want to weigh in
        on this question&hellip; but here is a start:</p>
        <ol>
            <li>To reflect the Love of God by creating an effective, powerful and emotionally
            safe environment for trainees to evaluate and overcome the broken parts of their
            lives so that freedom, joy, peace, and love become the cornerstones of their
            lives.</li>
            <li>Create an enduring ministry that outlasts any one key leader by:
                <ol type="a">
                    <li>Operating {PROGRAM_NAME} so that revenue exceeds expenses;</li>
                    <li>When the time is right, transfer Discovery! intellectual property,
                    licenses, software, and equipment to the next operating team at no cost.</li>
                </ol>
            </li>
        </ol>
        <p>We all believe that Discovery! is a much-needed ministry in our broken world. Do you
        remember the cleansing of your heart, the amazing and powerful freedom, love, and
        forgiveness we each experienced in this training? Our lives were changed forever!!! I
        thank God for Discovery!, and I know you do too, otherwise you would not be reading this.
        So, let&rsquo;s think big, and do something for Discovery! that has never been done
        before&hellip; GIVE IT AWAY&hellip; so that for generations, by God&rsquo;s grace,
        millions of people will experience the love of God and love for themselves&hellip; and
        with this new-found power and freedom, LOVE OTHERS!!!! This is the greatest
        commandment.</p>
        <p>This is a monumental vision. To give Discovery! away, as volunteers, it needs your
        prayers and your support. We need to find folks who believe in our mission and can give
        financially to the non-profit. If that might be you, or someone you know, please reach
        out to me to discuss the financial needs of the program. The program cannot open without
        financial support.</p>
        <p><strong>How will we accomplish this Mission?</strong></p>
        <ol type="a">
            <li>First, we will begin hosting Discovery! social gatherings to build vision and
            excitement, and renew old friendships (volunteers will be needed to organize and pull
            these events together).</li>
            <li>Hold fund-raisers to capture the financial support needed to open the program.
            All donations will go to the Discovery! 501(c)(3). Our goal is to secure sufficient
            funding to pay for the acquisition cost of the program, plus we have been advised
            that to responsibly host {PROGRAM_NAME} we need to raise $100,000 in cash-flow
            reserves to ensure the program survives.</li>
            <li>Begin the selection process for leadership teams. Previous leaders will have
            priority due to their experience, but the minimum expectation of all leadership is to
            have enrolled at least one trainee in The Beginning, or one couple in the Relationship training.
            We need Facilitators for Awakening, Vision, and Refocus. Initially, Max Thompson, Pamela
            Hafemann and I will be the lead facilitators in The Beginning and the Relationship training. But
            it is our desire to share this role with others who are qualified in the very near
            future. The Board of Directors will make final leadership selections.</li>
            <li>Begin a marketing campaign with the goal of hosting a Relationship training within
            the next four to six months, and to kick off The Beginning soon thereafter. Our goal is to have
            forty couples in the training room for the first Relationship training. We believe
            the need for relationship coaching is so significant that with the right marketing
            campaign, we can easily fill the seats and use the energy from that training to kick
            off The Beginning.</li>
        </ol>
        <p><strong>VOLUNTEERS NEEDED AS FOLLOWS:</strong></p>
        <ol type="a">
            <li>We need video and photography experts willing to work for free to help us put
            together an effective marketing campaign. Videography will include testimonials of
            enthusiastic trainees whose lives have been changed by the training. Relationship
            training videos and photography will be needed first.</li>
            <li>We need admin volunteers for the following:
                <ol>
                    <li>Skilled coaches to help trainees with registration and payment
                    confirmation;</li>
                    <li>Two volunteers to man the event sign-in table;</li>
                    <li>Greet and mingle with trainees at the clap-in;</li>
                    <li>Qualified security personnel to oversee the safety of the program.</li>
                </ol>
            </li>
            <li>We need someone to evaluate existing audio equipment and/or acquire additional
            equipment if needed.</li>
            <li>We need a place to store audio/video equipment and training supplies, and a means
            to transport this equipment if we cannot keep it at the hotel.</li>
            <li>We need someone to gather, organize, maintain and assemble the supplies needed
            for each training.</li>
        </ol>
        <p>Please let me know what role you may wish to play to open Discovery! Feel free to
        reach out to me with your thoughts at
        <a href="mailto:Kent@blueskyusa.net">Kent@blueskyusa.net</a>.</p>
        <p>Thank you again for your energy, your time, your heart, and your support.</p>
        <p>Blessings on you. I look forward to meeting you at our first Discovery! get-together,
        if not sooner.</p>
        <p>Take care,<br>Kent Hafemann</p>
    """

    text_content = f"""Dear {greeting},

Thanks for your continued interest in the {PROGRAM_NAME} launch.

So, what are the goals and mission for {PROGRAM_NAME}? Perhaps you may want to weigh in on this question... but here is a start:

1. To reflect the Love of God by creating an effective, powerful and emotionally safe environment for trainees to evaluate and overcome the broken parts of their lives so that freedom, joy, peace, and love become the cornerstones of their lives.
2. Create an enduring ministry that outlasts any one key leader by:
   a. Operating {PROGRAM_NAME} so that revenue exceeds expenses;
   b. When the time is right, transfer Discovery! intellectual property, licenses, software, and equipment to the next operating team at no cost.

We all believe that Discovery! is a much-needed ministry in our broken world. Do you remember the cleansing of your heart, the amazing and powerful freedom, love, and forgiveness we each experienced in this training? Our lives were changed forever!!! I thank God for Discovery!, and I know you do too, otherwise you would not be reading this. So, let's think big, and do something for Discovery! that has never been done before... GIVE IT AWAY... so that for generations, by God's grace, millions of people will experience the love of God and love for themselves... and with this new-found power and freedom, LOVE OTHERS!!!! This is the greatest commandment.

This is a monumental vision. To give Discovery! away, as volunteers, it needs your prayers and your support. We need to find folks who believe in our mission and can give financially to the non-profit. If that might be you, or someone you know, please reach out to me to discuss the financial needs of the program. The program cannot open without financial support.

HOW WILL WE ACCOMPLISH THIS MISSION?
a. First, we will begin hosting Discovery! social gatherings to build vision and excitement, and renew old friendships (volunteers will be needed to organize and pull these events together).
b. Hold fund-raisers to capture the financial support needed to open the program. All donations will go to the Discovery! 501(c)(3). Our goal is to secure sufficient funding to pay for the acquisition cost of the program, plus we have been advised that to responsibly host {PROGRAM_NAME} we need to raise $100,000 in cash-flow reserves to ensure the program survives.
c. Begin the selection process for leadership teams. Previous leaders will have priority due to their experience, but the minimum expectation of all leadership is to have enrolled at least one trainee in The Beginning, or one couple in the Relationship training. We need Facilitators for Awakening, Vision, and Refocus. Initially, Max Thompson, Pamela Hafemann and I will be the lead facilitators in The Beginning and the Relationship training. But it is our desire to share this role with others who are qualified in the very near future. The Board of Directors will make final leadership selections.
d. Begin a marketing campaign with the goal of hosting a Relationship training within the next four to six months, and to kick off The Beginning soon thereafter. Our goal is to have forty couples in the training room for the first Relationship training. We believe the need for relationship coaching is so significant that with the right marketing campaign, we can easily fill the seats and use the energy from that training to kick off D1.

VOLUNTEERS NEEDED AS FOLLOWS:
a. We need video and photography experts willing to work for free to help us put together an effective marketing campaign. Videography will include testimonials of enthusiastic trainees whose lives have been changed by the training. Relationship training videos and photography will be needed first.
b. We need admin volunteers for the following:
   1. Skilled coaches to help trainees with registration and payment confirmation;
   2. Two volunteers to man the event sign-in table;
   3. Greet and mingle with trainees at the clap-in;
   4. Qualified security personnel to oversee the safety of the program.
c. We need someone to evaluate existing audio equipment and/or acquire additional equipment if needed.
d. We need a place to store audio/video equipment and training supplies, and a means to transport this equipment if we cannot keep it at the hotel.
e. We need someone to gather, organize, maintain and assemble the supplies needed for each training.

Please let me know what role you may wish to play to open Discovery! Feel free to reach out to me with your thoughts at Kent@blueskyusa.net.

Thank you again for your energy, your time, your heart, and your support.

Blessings on you. I look forward to meeting you at our first Discovery! get-together, if not sooner.

Take care,
Kent Hafemann
"""

    return html_content, text_content


CONTRACT_REQUEST_SUBJECT = "Congratulations on completing your training!"

_LETTER_PARAS = (
    "Congratulations on completing your training... Woohoo!!! Let's keep going!!! "
    "From The Beginning through Vision, what you learned in each training is the foundation for the next. "
    "All these programs are fabulous and we look forward to seeing you there. "
    "Meanwhile, would you please help the Sojourn staff by taking a few minutes to update your "
    "pseudo name, Contract and as needed, other information from these programs. "
    "Our volunteers would otherwise have to type all of this into our records by hand, which "
    "takes many hours. We would be so grateful."
)
_LETTER_BULLETS = [
    "No password is needed, this link is just for you.",
    "Your words save automatically as you type, so you can stop and come back anytime using the same link.",
    "Fill in what you have so far and leave the rest blank. You can add to it after your later trainings.",
    "What you write is kept confidential and is used only for your training.",
]


_RESOURCES_PARA = (
    "We have also gathered books, podcasts and readings we recommend as you keep growing "
    "after your training. You will find them here, and we will keep adding more."
)


def contract_request_content(first_name, contracts_url, resources_url=None):
    """Returns (html_content, text_content) for the Contract Information Request -- the one letter
    used for every training. Sent automatically after a session ends (see app.py) and by the
    manual button on a contact's page (which also has a Preview). resources_url is the graduate's
    private link to the recommended-resources page; when it is None (nothing is shared yet) that part is left out."""
    import html as _html
    greeting = first_name.strip() if first_name and first_name.strip() else "Friend"
    g = _html.escape(greeting)
    body = _html.escape(_LETTER_PARAS).replace("...", "&hellip;")
    html_content = (
        f"<p>Dear {g},</p><p>{body}</p>"
        f'<p style="margin:18px 0"><a href="{contracts_url}" style="background:#3f5643; color:#ffffff; '
        'padding:12px 22px; border-radius:6px; text-decoration:none; font-weight:bold">Open your contact page</a></p>'
        "<ul>" + "".join(f"<li>{_html.escape(b)}</li>" for b in _LETTER_BULLETS) + "</ul>"
        + (f"<p>{_html.escape(_RESOURCES_PARA)}</p>"
           f'<p style="margin:18px 0"><a href="{resources_url}" style="background:#3f5643; color:#ffffff; '
           'padding:12px 22px; border-radius:6px; text-decoration:none; font-weight:bold">See our recommended resources</a></p>'
           if resources_url else "")
        + "<p>Thank you for helping us, and for the courage you are showing in this work.</p>"
        "<p>Have a great day,<br>Kent Hafemann</p>"
    )
    text_content = (
        f"Dear {greeting},\n\n{_LETTER_PARAS}\n\nOpen your contact page:\n{contracts_url}\n\n"
        + "".join(f"- {b}\n" for b in _LETTER_BULLETS)
        + (f"\n{_RESOURCES_PARA}\n{resources_url}\n" if resources_url else "")
        + "\nThank you for helping us, and for the courage you are showing in this work.\n\n"
        "Have a great day,\nKent Hafemann"
    )
    return html_content, text_content


# D5 (Refocus) has no contract, so it sends no letter.
COMPLETION_LETTER_CODES = ("D1", "D2", "D3", "D4", "D6")


def completion_letter_content(first_name, contracts_url, program_code, program_name=None, resources_url=None):
    """(subject, html, text) for the automatic letter after a training, or None if that program sends none."""
    code = (program_code or "").strip().upper()
    if code not in COMPLETION_LETTER_CODES:
        return None
    html_content, text_content = contract_request_content(first_name, contracts_url, resources_url)
    return CONTRACT_REQUEST_SUBJECT, html_content, text_content


# ---------------------------------------------------------------------------
# Session letters: the confirmation letters sent per training session (see app.py, "Letters").
# DRAFTS for Kent to revise. Placeholders: {first} {training} {dates} {where} {role} {duties}
# ({where} is " at <location>" or empty; {duties} is a ready-made sentence or empty).
# ---------------------------------------------------------------------------
SESSION_LETTERS = {
    "trainee_confirm": {
        "title": "Trainee Registration Confirmation",
        "audience": "Trainees",
        "subject": "You're confirmed for {training}",
        "paras": [
            "We are delighted to confirm your registration for The Art of Us, {dates}{where}.",
            "This will be a powerful experience for you and your partner, and we are honored that you have chosen to be part of it.",
            "Soon you will receive a separate email with your personal link to a questionnaire we ask you to seriously ponder. Take your time to complete each question. "
            "Let your experience, heart, and mind flow into your words. Be sure not to share your answers with your partner. "
            "Your thoughts are yours alone\u2026we want just your voice. The form is designed so you can close your work and "
            "pick up right where you left off by opening that same link again. For privacy, if you wish to create a password, please do so. "
            "Your password will be saved, so if you forget it, reply to this email and we will call to help.",
            "When we receive your completed questionnaire, we will email the program schedule, what to bring, and directions "
            "as the training gets closer.",
            "In the meantime, please hold these dates open. If anything changes for you, or if you have any questions at all, "
            "just reply to this email and let us know.",
            "We look forward to seeing you.",
        ],
        "signoff": "Warmly,",
        "signer": "Coach Kent and the Sojourn Team",
    },
    "seminar_registration": {
        "title": "Seminar registration",
        "audience": "Trainees",
        "subject": "Your registration for {training}",
        "paras": [
            "Thank you for registering for {training}, {dates}{where}.",
            "To complete your registration, please fill out your personal registration form at the link below. "
            "It covers your contact details, emergency contact and health information, and your answers save as you go.",
            "{link}",
            "Each of you will fill out your own form. A separate letter will follow with your questionnaire.",
            "If anything needs to change, or you have any questions, just reply to this email.",
        ],
        "signoff": "Warmly,",
    },
    "payment_reminder": {
        "title": "Payment reminder",
        "audience": "Trainees who have not paid",
        "subject": "A friendly reminder: payment for {training}",
        "paras": [
            "We are looking forward to {training}, {dates}{where}, and wanted to send a friendly reminder that "
            "we have not yet received your payment.",
            "{amount_sentence}",
            "Please complete your payment before the training so your place is fully secured. Please note that our team is not able to receive payment at the check-in table when you arrive. Please make your payment before the training so that check-in is quick and your place is secured. If you have already "
            "paid, thank you, and please disregard this note.",
            "If you have any questions, or would like to talk about payment options, just reply to this email.",
        ],
        "signoff": "Warmly,",
    },
    "payment_received": {
        "title": "Thank you \u2013 We\u2019re so excited",
        "audience": "Trainees who have paid",
        "subject": "Thank you \u2013 we\u2019re so excited to see you at {training}!",
        "paras": [
            "Thank you! We have received the payment for {training}, {dates}{where}, and we are so excited that you are coming.",
            "{partner_sentence}",
            "Your place is secured. If you have any questions, just reply to this email.",
            "We look forward to seeing you.",
        ],
        "signoff": "Warmly,",
    },
    "questionnaire_request": {
        "title": "Questionnaire request",
        "audience": "Trainees who have not completed the questionnaire",
        "subject": "Your questionnaire for {training}",
        "paras": [
            "We are looking forward to {training}, {dates}{where}. Here is your personal link to the questionnaire. Please take your time and answer it thoughtfully.",
            "{link}",
            "You can close it and pick up right where you left off by opening the same link again. "
            "This link is just for you, so please do not share it. Your answers help us prepare for you, and they are for you alone, so please answer in your own words.",
            "If you have any questions, just reply to this email.",
        ],
        "signoff": "Warmly,",
    },
    "questionnaire_reminder": {
        "title": "Questionnaire reminder",
        "audience": "Trainees who have not completed the questionnaire",
        "subject": "A friendly reminder: your questionnaire for {training}",
        "paras": [
            "We are looking forward to {training}, {dates}{where}, and wanted to remind you that we have not yet "
            "received your questionnaire (see link below).",
            "Your answers help us prepare for you, so please complete it before the training. It is for you alone, "
            "so please answer in your own words. If you have already done so, thank you, and please disregard this note.",
            "{link}",
            "You can close it and pick up right where you left off by opening the same link again.",
            "If you have any questions, just reply to this email.",
        ],
        "signoff": "Warmly,",
    },
    "what_to_bring": {
        "title": "What to bring",
        "audience": "Trainees",
        "subject": "What to bring to {training}",
        "paras": [
            "{training} begins soon, {dates}{where}. Here is how to be comfortable and ready.",
            "What to wear: Please wear comfortable, casual clothing and shoes. Tennis shoes are perfect. "
            "The training rooms are sometimes cool, so bring something warm to put on. If it is raining, bring an umbrella.",
            "Arriving: The training starts promptly, so please be at the training room door at least 10 minutes before the training starts.",
            "Friday: Come rested, hydrated and well nourished. {friday_end}",
            "If you have any questions, just reply to this email. We look forward to seeing you.",
        ],
        "signoff": "Warmly,",
    },
    "what_to_bring_aou": {
        "title": "What to Bring \u2013 The Art of Us",
        "audience": "Trainees",
        "subject": "What to bring to {training}",
        "paras": [
            "{training} begins soon, {dates}{where}. Here is how to be comfortable and ready.",
            "What to wear: Please wear comfortable, casual clothing and shoes. Tennis shoes are perfect. "
            "The training rooms are sometimes cool, so bring something warm to put on. If it is raining, bring an umbrella.",
            "Arriving: The training starts promptly, so please be at the training room door at least 10 minutes before the training starts.",
            "Friday: Come rested, hydrated and well nourished. {friday_end}",
            "If you have any questions, just reply to this email. We look forward to seeing you.",
        ],
        "signoff": "Warmly,",
    },
    # ---- The same trainee letters for every training EXCEPT The Art of Us (couples). The Art of Us keeps the originals above. ----
    "seminar_registration_other": {
        "title": "Seminar registration \u2013 Other Trainings",
        "audience": "Trainees",
        "subject": "Your registration for {training}",
        "paras": [
            "Thank you for registering for {training}, {dates}{where}.",
            "To complete your registration, please fill out your personal registration form at the link below. "
            "It covers your contact details, emergency contact and health information, and your answers save as you go.",
            "{link}",
            "A separate letter will follow with your questionnaire.",
            "If anything needs to change, or you have any questions, just reply to this email.",
        ],
        "signoff": "Warmly,",
    },
    "trainee_confirm_other": {
        "title": "Trainee Registration Confirmation \u2013 Other Trainings",
        "audience": "Trainees",
        "subject": "You're confirmed for {training}",
        "paras": [
            "We are delighted to confirm your registration for {training}, {dates}{where}.",
            "This will be a powerful experience for you, and we are honored that you have chosen to be part of it.",
            "Soon you will receive a separate email with your personal link to a questionnaire we ask you to seriously ponder. Take your time to complete each question. "
            "Let your experience, heart, and mind flow into your words. "
            "Your thoughts are yours alone\u2026we want just your voice. The form is designed so you can close your work and "
            "pick up right where you left off by opening that same link again. For privacy, if you wish to create a password, please do so. "
            "Your password will be saved, so if you forget it, reply to this email and we will call to help.",
            "When we receive your completed questionnaire, we will email the program schedule, what to bring, and directions "
            "as the training gets closer.",
            "In the meantime, please hold these dates open. If anything changes for you, or if you have any questions at all, "
            "just reply to this email and let us know.",
            "We look forward to seeing you.",
        ],
        "signoff": "Warmly,",
        "signer": "Coach Kent and the Sojourn Team",
    },
    "payment_reminder_other": {
        "title": "Payment reminder \u2013 Other Trainings",
        "audience": "Trainees who have not paid",
        "subject": "A friendly reminder: payment for {training}",
        "paras": [
            "We are looking forward to {training}, {dates}{where}, and wanted to send a friendly reminder that "
            "we have not yet received your payment.",
            "{amount_sentence}",
            "Please complete your payment before the training so your place is fully secured. Please note that our team is not able to receive payment at the check-in table when you arrive. Please make your payment before the training so that check-in is quick and your place is secured. If you have already "
            "paid, thank you, and please disregard this note.",
            "If you have any questions, or would like to talk about payment options, just reply to this email.",
        ],
        "signoff": "Warmly,",
    },
    "payment_received_other": {
        "title": "Thank you \u2013 We\u2019re so excited \u2013 Other Trainings",
        "audience": "Trainees who have paid",
        "subject": "Thank you \u2013 we\u2019re so excited to see you at {training}!",
        "paras": [
            "Thank you! We have received the payment for {training}, {dates}{where}, and we are so excited that you are coming.",
            "Your place is secured. If you have any questions, just reply to this email.",
            "We look forward to seeing you.",
        ],
        "signoff": "Warmly,",
    },
    "questionnaire_request_other": {
        "title": "Questionnaire request \u2013 Other Trainings",
        "audience": "Trainees who have not completed the questionnaire",
        "subject": "Your questionnaire for {training}",
        "paras": [
            "We are looking forward to {training}, {dates}{where}. Here is your personal link to the questionnaire. Please take your time and answer it thoughtfully.",
            "{link}",
            "You can close it and pick up right where you left off by opening the same link again. "
            "This link is just for you, so please do not share it. Your answers help us prepare for you, and they are for you alone, so please answer in your own words.",
            "If you have any questions, just reply to this email.",
        ],
        "signoff": "Warmly,",
    },
    "questionnaire_reminder_other": {
        "title": "Questionnaire reminder \u2013 Other Trainings",
        "audience": "Trainees who have not completed the questionnaire",
        "subject": "A friendly reminder: your questionnaire for {training}",
        "paras": [
            "We are looking forward to {training}, {dates}{where}, and wanted to remind you that we have not yet "
            "received your questionnaire (see link below).",
            "Your answers help us prepare for you, so please complete it before the training. It is for you alone, "
            "so please answer in your own words. If you have already done so, thank you, and please disregard this note.",
            "{link}",
            "You can close it and pick up right where you left off by opening the same link again.",
            "If you have any questions, just reply to this email.",
        ],
        "signoff": "Warmly,",
    },
    "ta_invitation": {
        "title": "TA invitation",
        "audience": "People invited to be a TA",
        "subject": "You're invited to serve as a TA for {training}",
        "button": "Let us know if you can join us",
        "paras": [
            "TAs are the heartbeat of a Sojourn training. We believe the training's effectiveness depends on your skill, your ability and your leadership.",
            "That is why we have chosen you to be a TA for {training}.",
            "We so appreciate your work, your dedication and your skill as you partner with us to bring healing and wholeness to the world.",
            "Please let us know whether you can join us on {dates}{where} by clicking the button below. If anything changes for you, just let us know.",
            "{link}",
            "Thanks so much.",
        ],
        "signoff": "God bless you,",
        "signer": "The Sojourn Team",
    },
    "facilitator_confirm": {
        "title": "Facilitator confirmation",
        "audience": "Facilitators",
        "subject": "Thank you for facilitating {training}",
        "paras": [
            "Thank you for saying yes to serving as {role} for {training}, {dates}{where}.",
            "Your experience and your presence make all the difference to the people who will be in the room.",
            "Please hold these dates open. We will send the full schedule and team assignments before the training. "
            "If you have a conflict or a question, reply to this email so we can plan around it.",
            "Thank you for your commitment to this work.",
        ],
        "signoff": "With gratitude,",
    },
    "ta_confirm": {
        "title": "TA confirmation",
        "audience": "TAs",
        "subject": "You're confirmed as a TA for {training}",
        "paras": [
            "Thank you for serving as a TA for {training}, {dates}{where}.",
            "{duties}",
            "TAs are the heart of how participants feel supported. We will send arrival times, the schedule and "
            "what to bring before the training.",
            "Please hold these dates open. If you have a conflict or a question, reply to this email and let us know.",
        ],
        "signoff": "With gratitude,",
    },
    "backup_confirm": {
        "title": "Back-up TA confirmation",
        "audience": "Back-up TAs",
        "subject": "Thank you for being a back-up TA for {training}",
        "paras": [
            "Thank you for being willing to serve as a back-up TA for {training}, {dates}{where}.",
            "As a back-up, you will step in if one of our TAs is unable to attend, so please try to keep these dates "
            "open. We will let you know as soon as we need you.",
            "If your plans change, or you have a question, just reply to this email.",
            "We are grateful for your willingness to serve.",
        ],
        "signoff": "With gratitude,",
    },
}
SESSION_TRAINEE_LETTERS = ["seminar_registration", "trainee_confirm", "payment_reminder", "payment_received", "questionnaire_request", "questionnaire_reminder", "what_to_bring"]
# Each trainee letter above is the one used for The Art of Us (couples; "What to bring" uses its own Art of Us copy).
# Every other training uses the "_other" copy below. Sending records stay under the letter's main name above.
OTHER_VARIANTS = {k: k + "_other" for k in ("seminar_registration", "trainee_confirm", "payment_reminder", "payment_received", "questionnaire_request", "questionnaire_reminder")}
ART_OF_US_CODE = "D4"


def content_key(key, program_code):
    """The letter whose wording is used for this program: Art of Us (D4) gets the originals, everything else the other copies."""
    if key == "what_to_bring":
        return "what_to_bring_aou" if program_code == ART_OF_US_CODE else "what_to_bring"
    if key in OTHER_VARIANTS and program_code != ART_OF_US_CODE:
        return OTHER_VARIANTS[key]
    return key

SESSION_LETTER_ORDER = SESSION_TRAINEE_LETTERS + ["facilitator_confirm", "ta_invitation", "ta_confirm", "backup_confirm"]


# The letters the Ambassador-call flow sends. Same shape as the session letters, so they can be edited the same way.
# "greeting" is the word before the name; {vol_name} etc. fill in from the Ambassador who took the request.
GUIDE_LETTERS = {
    "guide_curious": {
        "title": "Reply to \"I'm curious\"",
        "audience": "People who ask to be called",
        "greeting": "Hi",
        "subject": "{vfirst} from Sojourn will {pw} you soon",
        "paras": [
            "Thank you for your interest in {label}. We\u2019re so glad you\u2019re curious!",
            "**{vol_name}**, an experienced Sojourn volunteer, will {pw} you from **{vphone}**, usually within a few hours. "
            "We reach out between 8 am and 8 pm Central, so if you asked in the evening, expect to hear from {vfirst} the next morning. "
            "For your security, here is their name and number, so you will know it is us.",
            "There is no pressure at all. It\u2019s just a conversation with someone who has been through this training and is "
            "excited to share how it changed their life. Ask anything you like.",
            "If it isn\u2019t a good time, just reply to this email and we\u2019ll find a better one.",
            "If you decide you\u2019re ready, {vfirst} can send you a personal link to reserve your spot. Your information is "
            "already filled in, and you only choose a date. Payment comes later. After you register, you\u2019ll receive a separate "
            "email with a private link to a questionnaire. You can close it and pick up where you left off at any time.",
            "We\u2019re looking forward to meeting you!",
        ],
        "signoff": "Warmly,",
        "signer": "The Sojourn Team",
    },
    "guide_register": {
        "title": "Registration link",
        "audience": "People an Ambassador has talked with",
        "greeting": "Hi",
        "subject": "Your personal link to reserve your spot \u2013 {label}",
        "paras": [
            "It was good to connect. As promised, here is your personal link to reserve your spot in **{label}**:",
            "{link}",
            "It already has your information filled in. Just choose your date and confirm. Payment comes later; we will send you the details.",
            "If you have any questions, reply to this email or call {vfirst} at {vphone}.",
        ],
        "signoff": "Warmly,",
        "signer": "{vol_name} and the Sojourn Team",
    },
    "guide_questionnaire": {
        "title": "Questionnaire link",
        "audience": "People who have reserved",
        "greeting": "Hi",
        "subject": "Your personal questionnaire link \u2013 {label}",
        "paras": [
            "Here is your personal link to the questionnaire for **{label}**. Please take your time and answer it thoughtfully.",
            "{link}",
            "You can close it and pick up right where you left off by opening the same link again. "
            "This link is just for you, so please don\u2019t share it.",
            "Questions? Reply to this email or call {vfirst} at {vphone}.",
        ],
        "signoff": "Warmly,",
        "signer": "{vol_name} and the Sojourn Team",
    },
    "guide_longform": {
        "title": "Complete your profile",
        "audience": "People who have reserved",
        "greeting": "Hi",
        "subject": "Please complete your information \u2013 {label}",
        "paras": [
            "Thank you for reserving your spot in **{label}**! One more thing before the training: please take a few minutes to "
            "complete your contact information, including a photo, so we can welcome you properly.",
            "{link}",
            "You can stop at any time and pick up where you left off by opening the same link again.",
            "Questions? Reply to this email or call {vfirst} at {vphone}.",
        ],
        "signoff": "Warmly,",
        "signer": "{vol_name} and the Sojourn Team",
    },
    "profile_request": {
        "title": "Profile update request (email, text and the profile page)",
        "audience": "Any contact: ambassadors, sponsors, trainees, team",
        "greeting": "",
        "subject": "We Appreciate Your Help!",
        "paras": [
            "Dear {First name},",
            "Please take a moment to update your contact information below. It only takes a few minutes. "
            "Your updated information will keep you connected with your fellow participants and team members, "
            "and ease some Sojourn admin burden.",
            "{link}",
            "Your answers save as you go. You can close the page and pick up right where you left off by opening the same link again.",
        ],
        "signoff": "Thanks so much, and have a great day!",
        "signer": "The Sojourn Team",
    },
    "testimonial_request": {
        "title": "Testimonial request (email)",
        "audience": "Former trainees and volunteers you invite to share their story",
        "greeting": "Hi",
        "subject": "Share your experience",
        "paras": [
            "You may have heard we are inviting former trainees & volunteers to share how the program has touched their lives, "
            "and the lives of their family and friends. We'd love to hear about your experience with the training. It only takes a "
            "couple of minutes. You can speak it, type it, or record yourself. Your story may help someone else take their first step.",
            "{link}",
            "Your story will not be published without your approval. We'll show you the final edited version first, and when "
            "approved by you, we will add it to other testimonials that are ready to be added to the website.",
            "When you have a free moment, please take a look at {home_url} to see the new direction we are heading with Sojourn. "
            "The program names and branding are very different from the past.{stories_sentence}",
        ],
        "signoff": "Thank you so much,",
        "signer": "Kent",
    },
    "needs_request": {
        "title": "Food and physical needs request (session team)",
        "audience": "Team members on a session who have not answered",
        "greeting": "Hi",
        "subject": "A quick question before the training",
        "paras": [
            "Thank you for being part of the team! So that we can plan meals, rooms and activities, please tell us about any "
            "food allergies or dietary restrictions, food preferences, accessibility or room needs, and any injuries that limit everyday activities.",
            "It only takes a minute. Please use your private link, and scroll to the food and health questions:",
            "{link}",
            "Your answers save as you go. You can close the page and pick up right where you left off by opening the same link again.",
        ],
        "signoff": "Thanks so much,",
        "signer": "The Sojourn Team",
    },
    "chat_private_alert": {
        "title": "Private message alert (email)",
        "audience": "Team members who have a new private message",
        "greeting": "Hi",
        "subject": "You have a new private message in the Hub",
        "paras": [
            "Someone on the team sent you a private message in the Hub. For privacy, the message itself is not in this email.",
            "Sign in to read it:",
            "{link}",
            "You will get at most one of these an hour. You can turn these emails off on the Private Messages page.",
        ],
        "signoff": "Thank you,",
        "signer": "The Sojourn Team",
    },
    "chat_private_alert_text": {
        "title": "Private message alert (text message)",
        "audience": "Team members who chose to get texts",
        "greeting": "Hi",
        "subject": "Text message",
        "paras": [
            "you have a new private message in the Hub. Sign in to read it: {link}",
        ],
        "signoff": "",
        "signer": "",
    },
    "trainee_resources": {
        "title": "After the training: recommended resources",
        "audience": "Paid trainees, when their training ends",
        "greeting": "Dear",
        "subject": "Thank you for being part of {label}",
        "paras": [
            "Thank you for being part of {label}. We are so glad you were with us.",
            "We have gathered books, podcasts and readings we recommend as you keep growing. You will find them here, and we will keep adding more.",
            "{link}",
            "This page is private to you, so please don't share the link. If you have any questions, just reply to this email.",
        ],
        "button": "See our recommended resources",
        "signoff": "Have a great day,",
        "signer": "Kent Hafemann",
    },
    "site_invitation": {
        "title": "Invitation to the private website preview",
        "audience": "Friends you invite to see the website before it opens to everyone",
        "greeting": "Hi",
        "subject": "You're invited to preview our new website",
        "paras": [
            "We are getting ready to open our new website, and I would love for you to be one of the first to see it. It is not open to the public yet, so this invitation is just for you.",
            "{link}",
            "This link is private to you, so please don't share it. If you have any questions or thoughts, just reply to this email. I would love to hear what you think.",
        ],
        "button": "Preview the website",
        "signoff": "Warmly,",
        "signer": "Kent Hafemann",
    },
    "pledge_thanks": {
        "title": "Thank you for your pledge (fundraising site)",
        "audience": "People who pledge on the Discovery Legacy fundraising website",
        "greeting": "Dear",
        "subject": "Thank you for being a Founding Friend",
        "paras": [
            "Thank you for pledging {amount_text} to Discovery Legacy. Your belief in this work means more than we can say.",
            "A pledge is a statement of your intention, not a payment, and you will not be asked to give until our bank account is open. We will write to you then with the details, and we will keep you updated as we get ready to open in 2027.",
            "Until the IRS recognizes our application for tax-exempt status, we cannot tell you that gifts are tax-deductible. We will let you know when that changes.",
        ],
        "signoff": "With gratitude,",
        "signer": "The Discovery Legacy Team",
    },
    "video_call": {
        "title": "Video call link (Google Meet)",
        "audience": "Any contact",
        "greeting": "Hi",
        "subject": "Our video call",
        "paras": [
            "Here is the link for our video call{when_text}:",
            "{link}",
            "Just click the link a few minutes before we start. It works in your web browser on a computer, phone or tablet \u2014 nothing to install.",
        ],
        "signoff": "Looking forward to seeing you,",
        "signer": "Kent",
    },
    "guide_payment": {
        "title": "Payment request",
        "audience": "People who have reserved",
        "greeting": "Hi",
        "subject": "Your payment for {label}",
        "paras": [
            "Thank you for reserving your spot in **{label}**! The next step is payment, which secures your place.",
            "The training fee is $1,299 per couple (one payment covers both partners). Reply to this email or call {vfirst} at "
            "{vphone} and we will walk you through the easy ways to pay.",
            "Please note that our team is not able to receive payment at the check-in table when you arrive. Please make your payment before the training so that check-in is quick and your place is secured.",
            "Once your payment arrives, you will receive a confirmation from us.",
        ],
        "signoff": "Warmly,",
        "signer": "{vol_name} and the Sojourn Team",
    },
    "guide_payment_reminder": {
        "title": "Payment reminder (from the Ambassador)",
        "audience": "People who have reserved but not paid",
        "greeting": "Hi",
        "subject": "A friendly reminder about your payment \u2013 {label}",
        "paras": [
            "Just a friendly reminder that your payment for **{label}** has not come in yet. Your spot is held, and we are looking "
            "forward to seeing you.",
            "Please note that our team is not able to receive payment at the check-in table when you arrive. Please make your payment before the training so that check-in is quick and your place is secured.",
            "If you have any questions about paying, or if something is in the way, reply to this email or call {vfirst} at {vphone}. "
            "We are glad to help.",
        ],
        "signoff": "Warmly,",
        "signer": "{vol_name} and the Sojourn Team",
    },
    "sponsor_welcome": {
        "title": "Sponsor welcome (complete your profile)",
        "audience": "Volunteers who sponsor someone",
        "greeting": "Dear",
        "subject": "Thank you for sponsoring {client}",
        "paras": [
            "It is because of volunteers like you that Sojourn flourishes, and we are so grateful for your leadership and giving heart. "
            "We have automated much of the sponsorship process so that everyone can complete the entire sponsorship process without admin support.",
            "Here is how it works:",
            "1. As a sponsor, you complete a short form registration for the sponsee.",
            "2. You complete your contact information (this eliminates admin support). Here is your link:",
            "{link}",
            "Please complete the items marked in color on that form. Everything else is optional.",
            "Your answers save as you go. You can close the page and pick up right where you left off by opening the same link again.",
            "3. When your contact form is complete, Sojourn will automatically send you a dedicated web page to your phone and computer which enables you "
            "(simply by clicking on buttons) to easily walk the sponsee through the registration process. Of course, if you need help speaking to the sponsee, "
            "let us know (again by clicking on a button) and an experienced volunteer will reach out to you.",
            "Thank you so much. Let us know if you have questions.",
        ],
        "signoff": "Have a great day.",
        "signer": "The Sojourn Team",
    },
    "sponsor_page": {
        "title": "Sponsor thank-you and page (contact form complete)",
        "audience": "Volunteers who sponsor someone",
        "greeting": "Dear",
        "subject": "Your page for {client}",
        "paras": [
            "Thank you for completing your contact form.",
            "Here is your dedicated web page for {client}. Use it on your phone or computer. Simply by clicking on buttons you can easily walk {client} "
            "through the registration process. If you need help speaking to them, let us know (again by clicking on a button) and an experienced "
            "volunteer will reach out to you.",
            "{page_link}",
            "This page is yours alone, so please do not share the link. Thank you so much for sponsoring.",
        ],
        "signoff": "Have a great day.",
        "signer": "The Sojourn Team",
    },
}
GUIDE_FIELDS = ("when_text", "First Name", "first name", "label", "vol_name", "vfirst", "vphone", "link", "pw", "first", "First name", "Name", "name", "client", "page_link", "amount_text")
ALL_LETTERS = {**SESSION_LETTERS, **GUIDE_LETTERS}


def allowed_fields(key):
    return GUIDE_FIELDS if key in GUIDE_LETTERS else LETTER_FIELDS


# ---- editable wording: the app registers a loader that returns the saved edit for a letter (or None) ----
_OVERRIDE = {"loader": None}
LETTER_FIELDS = ("first", "First name", "Name", "name", "training", "dates", "where", "role", "duties", "link", "amount_sentence", "partner_sentence", "friday_end")


def set_override_loader(fn):
    _OVERRIDE["loader"] = fn


def saved_edit(key):
    """The saved edit for a letter: {'subject','body','signoff','signer'} or None."""
    fn = _OVERRIDE["loader"]
    if not fn:
        return None
    try:
        return fn(key)
    except Exception:
        return None


def spec_with_edit(key, edit):
    spec = dict(ALL_LETTERS[key])
    if edit:
        spec["subject"] = edit["subject"]
        spec["paras"] = [x.strip() for x in (edit["body"] or "").replace("\r\n", "\n").split("\n\n") if x.strip()]
        if edit.get("signoff") is not None:
            spec["signoff"] = edit["signoff"]
        if edit.get("signer") is not None:
            spec["signer"] = edit["signer"]
    return spec


def original_body(key):
    return "\n\n".join(ALL_LETTERS[key]["paras"])


def fill_for(first_name, training, dates, location=None, role=None, duties=None, link=None, partner=None, amount=None, friday_end=None):
    greeting = first_name.strip() if first_name and first_name.strip() else "Friend"
    duty_list = [d for d in (duties or []) if d and d != "Not confirmed"]
    if duty_list:
        duties_sentence = ("Your assignment is " if len(duty_list) == 1 else "Your assignments are ") + ", ".join(duty_list) + "."
    else:
        duties_sentence = "Your specific assignment will be confirmed before the training."
    return {
        "first": greeting, "training": training, "dates": dates,
        "where": f" at {location}" if location else "",
        "role": role or "a facilitator", "duties": duties_sentence,
        "link": link or "[their personal link]",
        "amount_sentence": (f"The training fee is {amount}, and one payment covers both partners."
                            if amount else ""),
        "partner_sentence": (f"This payment covers you and {partner}, so you are both all set."
                             if partner else ""),
        "friday_end": friday_end or "",
    }


def render_spec(spec, fill, link=None):
    import html as _html
    import re as _re
    fill = dict(fill)
    fill.setdefault("Name", fill.get("first", ""))
    fill.setdefault("name", fill.get("first", ""))
    fill.setdefault("home_url", "our website")
    fill.setdefault("stories_url", "what others are saying")
    fill.setdefault("stories_sentence", "")
    fill.setdefault("First name", fill.get("first", ""))
    fill.setdefault("First Name", fill.get("first", ""))
    fill.setdefault("first name", fill.get("first", ""))
    greeting = fill["first"]
    word = spec.get("greeting", "Dear")
    subject = spec["subject"].format(**fill)
    signoff = spec["signoff"].format(**fill)
    signer = spec.get("signer", "Kent Hafemann").format(**fill)
    paras = [p for p in (p.format(**fill).strip() for p in spec["paras"]) if p]

    def h(p):
        return _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", _html.escape(p))
    open_html = f"<p>{_html.escape(word)} {_html.escape(greeting)},</p>" if word else ""
    open_text = f"{word} {greeting},\n\n" if word else ""
    html_content = (
        open_html
        + "".join(
            (f'<p style="margin:18px 0"><a href="{_html.escape(p)}" style="background:#3f5446;color:#ffffff;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:600;display:inline-block">{_html.escape(spec["button"])}</a></p>'
             if (link and p == link and spec.get("button"))
             else f'<p><a href="{_html.escape(p)}">{_html.escape(p)}</a></p>' if ((link and p == link) or (fill.get("page_link") and p == fill.get("page_link")))
             else f"<p>{h(p)}</p>") for p in paras)
        + f"<p>{_html.escape(signoff)}<br>{_html.escape(signer)}</p>"
    )
    text_content = (open_text + "\n\n".join((f'{spec["button"]}: {p}' if (link and p == link and spec.get("button")) else p.replace("**", "")) for p in paras)
                    + f"\n\n{signoff}\n{signer}")
    return subject, html_content, text_content


def guide_letter_content(key, first, label, vol_name, vphone, pw=None, link=None, **extra):
    """(subject, html, text) for an Ambassador-call letter, using any saved edit and falling back to the original."""
    vfirst = (vol_name or "").split()[0] if (vol_name or "").strip() else ""
    fill = {"first": first, "label": label, "vol_name": vol_name, "vfirst": vfirst, "vphone": vphone,
            "link": link or "", "pw": pw or "call or text", "client": "", "page_link": "", "when_text": ""}
    fill.update({k: (v or "") for k, v in extra.items()})
    edit = saved_edit(key)
    if edit:
        try:
            return render_spec(spec_with_edit(key, edit), fill, link)
        except Exception:
            pass
    return render_spec(GUIDE_LETTERS[key], fill, link)


def profile_request_parts(first, link=""):
    """The wording of the profile-update request, from the Correspondence page (or the original).
    Used for the Email / Text buttons on a contact and for the top of the public profile page."""
    fill = {"first": (first or "").strip() or "Friend", "label": "", "vol_name": "", "vfirst": "", "vphone": "",
            "link": link or "", "pw": "", "client": "", "page_link": "", "when_text": "",
            "First name": (first or "").strip() or "Friend", "First Name": (first or "").strip() or "Friend",
            "first name": (first or "").strip() or "Friend"}
    spec = GUIDE_LETTERS["profile_request"]
    edit = saved_edit("profile_request")
    if edit:
        try:
            spec = spec_with_edit("profile_request", edit)
            spec["subject"].format(**fill)
        except Exception:
            spec = GUIDE_LETTERS["profile_request"]
    subject, _html, text = render_spec(spec, fill, link)
    paras = [p.format(**fill).strip().replace("**", "") for p in spec["paras"]]
    body = [p for p in paras if p and p != (link or "\0") and "{link}" not in p]
    return {"subject": subject, "text": text, "html": _html, "heading": subject, "greeting": spec.get("greeting", "Dear") if "greeting" in spec else "Dear",
            "name": fill["first"], "paras": body, "signoff": spec["signoff"].format(**fill),
            "signer": spec.get("signer", "").format(**fill)}


def session_letter_content(key, first_name, training, dates, location=None, role=None, duties=None, link=None,
                           partner=None, amount=None, friday_end=None):
    """(subject, html, text) for one session letter, or None for an unknown key.
    Uses the wording saved on the Correspondence page; falls back to the original if that wording cannot be used."""
    if key not in SESSION_LETTERS:
        return None
    fill = fill_for(first_name, training, dates, location, role, duties, link, partner, amount, friday_end)
    edit = saved_edit(key)
    if edit:
        try:
            return render_spec(spec_with_edit(key, edit), fill, link)
        except Exception:
            pass
    return render_spec(SESSION_LETTERS[key], fill, link)

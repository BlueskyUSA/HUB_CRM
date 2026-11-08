"""Owner-only 'How the site works' guide: what each feature does, where to find it, who can use it, and what it
connects to. The page is at /crm/feature-guide and a PDF copy is at /crm/feature-guide.pdf.

KEEP THIS CURRENT: whenever a feature is added or changed, add or edit its entry below and bump GUIDE_UPDATED.
Each entry: name, where (menu path or web address), who (who can use it), what (plain English), connects (tables,
emails, other features)."""
import io
from flask import render_template, send_file

GUIDE_UPDATED = "October 31, 2026"

E = lambda name, where, who, what, connects="": dict(name=name, where=where, who=who, what=what, connects=connects)

SECTIONS = [
    ("public", "The public website", "What visitors see. No login needed. The brand on every public page is written Discovery!", [
        E("Home page and menu", "The web address itself (/)", "Anyone",
          "The front page, the main menu with the four programs, and a menu bar that reappears after scrolling on the main public pages.",
          "Menu subtitles and program pages are in the templates; upcoming dates come from Programs and Sessions."),
        E("Program pages (The Art of Us, The Beginning, Awakening, Vision)", "/programs, then a program", "Anyone",
          "One page per program with what it is, who it is for, what is included, upcoming dates and the cost. The Art of Us page also has the Is This for You? section.",
          "Dates come from the sessions entered in the CRM (Programs). Prices are written in the page templates and the training fee setting."),
        E("What's included", "/programs/<program>/whats-included", "Anyone", "The detail page for what a program includes."),
        E("Our story, Meet the team, About the program", "/our-story, /meet-the-team, /about-the-program", "Anyone",
          "The founder story, the team page and the explanation of the program.",
          "The team page is fed by Admin > Leadership (Website) and the contacts' photos."),
        E("Register / I'm interested", "/register", "Anyone",
          "Lets someone ask about a program or register interest. Creates or updates a contact and starts the follow-up.",
          "Creates a contact (marketing source recorded) and an interest log entry; the Excitement or thank-you emails can follow."),
        E("Contact us", "/contact", "Anyone", "A general contact form. Adds a contact for follow-up.", "contacts"),
        E("Talk to us (the Curious form)", "/talk-to-us", "Anyone",
          "The form for someone who wants to hear from an experienced Discovery! volunteer by text or phone. Starts the Guides call flow.",
          "call_requests, interest_log; alerts the Guides; see Discovery Guides."),
        E("Donate", "/donate", "Anyone", "The donation page. Records the person as a contact.", "contacts, donations"),
        E("Stories (In Their Own Words)", "/stories", "Anyone, only when switched on",
          "Approved testimonials. Hidden everywhere on the site until the Owner or Leadership turns the stories switch on (default is off).",
          "Switch is on the Testimonials page; setting stored in app_settings (stories_visible)."),
        E("Discovery volunteer invitation", "/discovery", "Past Discovery volunteers and TAs",
          "A focused page for past volunteers and TAs to add themselves. Chosen roles include Interested Party.", "contacts"),
    ]),
    ("private_links", "Private links people receive", "Links with a private code in them. Only the person who got the link can use it.", [
        E("Complete your profile", "/complete-profile (public link) or /complete-profile/<code> (personal link)", "The person who got the link",
          "The long form that gathers a person's details, history and agreements. The public link can be posted on social media or in a general email. Includes the question about attending a Discovery training.",
          "Fills in the contact, training_profiles and contracts."),
        E("Connect with us", "/connect/<code>", "The person who got the Excitement email", "A one-click page that tells us the person wants to be contacted.", "Shows up under Contact requests."),
        E("Request the preliminary plan", "/discovery/plan/<code>", "The person who got the long-form thank-you email", "Lets the person ask for the business plan.", "Business plan email and the contacts record."),
        E("Questionnaire", "/questionnaire/<code>", "One trainee", "A trainee answers their own questionnaire privately. Nobody else, including a partner, can see the answers from here.", "feedback_responses, enrollments."),
        E("Feedback form", "/feedback/<code>", "One trainee", "The after-training feedback form.", "feedback_responses."),
        E("Share your experience", "/share/<code>, or /share for the open link", "The person invited, or anyone with the open link",
          "Lets a person type, dictate or record a testimonial and choose how their name appears. Open-link submissions ask for a name and email or phone.",
          "testimonials. See Testimonials."),
        E("Reserve a spot", "/reserve/<code>", "The person a Guide sent it to", "Enrolls the person (and partner) or puts them on the waitlist when the date is full.", "enrollments."),
        E("Unsubscribe", "/unsubscribe/<code>", "Any email recipient", "Every email blast has an unsubscribe link. The person is taken off future blasts.", "contacts (email status)."),
    ]),
    ("contacts", "Contacts and people", "Everyone we know.", [
        E("Contacts", "Contacts (main menu)", "Leadership, or anyone given the Contacts area",
          "The list and the record for each person: details, history, sponsor, photo, data sources, letters sent, enrollments, contracts and donations. Add, edit and (Leadership) delete.",
          "contacts, contact_lists, enrollments, contracts, donations."),
        E("Contact requests", "Admin > Contact requests", "Contacts area", "Everyone who clicked Connect with us in an email and has not yet been answered. Mark each one resolved.", "contacts (contact request flag)."),
        E("Sponsor pipeline", "Admin > Sponsor pipeline", "Contacts area", "Who brought whom in, and where each person is on the path to leading.", "contacts (sponsor), enrolled-by tracking."),
        E("Data Sources", "Admin > Data Sources", "Leadership", "Named groups of contacts, such as Kent's Contact Data, the Discovery Contact list and Responded to the Excitement blast. A person can be in more than one. Used to choose who receives a blast.", "contact_lists, contact_list_members."),
        E("Calendar", "Reached from the Contacts area", "Contacts area", "A calendar view of scheduled sessions.", "cohorts."),
        E("Brought in by (bulk)", "Reached from the Contacts area", "Contacts area", "Fills in who brought in several people at once.", "contacts."),
    ]),
    ("programs", "Programs and sessions", "What we teach and when.", [
        E("Programs", "Programs (main menu)", "Leadership, or anyone given a program area",
          "The trainings, their scheduled sessions (dates, capacity), small groups and the people enrolled and on the team. Quick schedule adds sessions fast. Enroll people, record payments, print the team list.",
          "programs, cohorts, enrollments, cohort_staffing, small_groups."),
        E("Program materials", "Programs > a program > Syllabus / Music / Handouts / Other / Movies", "Anyone given that heading for that program",
          "Training materials for each program. Access is granted heading by heading, and people with access can view but not download.",
          "program_materials, program_playlists, playlist_songs, program_movies."),
        E("Session letters", "Programs > a session > Letters", "Leadership with Contacts access", "Preview, test and send the letters that go to the people in a session (welcome, venue, reminders).", "Email through Brevo."),
        E("Food, access and activity needs", "Asked on the long profile form and on each trainee's questionnaire; shown on a session page under the roster", "Entered by the person or by staff on Edit Contact; the session summary is for Leadership only",
          "Food allergies and dietary needs, accessibility or room needs (such as a wheelchair-accessible room), and injuries that limit everyday activities (such as sitting on the floor). The session page lists everyone who gave an answer, for the hotel's meal counts and room requests. The venue letter also asks couples to share these.",
          "contacts (dietary_needs, access_needs, activity_limits); the venue letter in Programs > a session > Letters."),
        E("Feedback", "Leadership area", "Leadership", "The feedback and questionnaire answers people gave after trainings.", "feedback_responses."),
        E("Contracts and business plan", "Reached from the Contacts area", "Contracts area", "The agreements people sign and the earlier versions, and the business plan page.", "contracts, contract_revisions."),
    ]),
    ("guides", "Discovery Guides (the call flow)", "How a curious visitor gets a personal answer quickly.", [
        E("Curious form to a Guide", "Public Talk to us form, then Admin > Call requests", "Guides and Leadership",
          "A visitor asks to be contacted by text or phone. The next Guide in turn is alerted, opens a private call page, makes the contact and can send the video link, the questionnaire and the reserve link from there. Unanswered requests move to the next Guide.",
          "call_requests, call_notices; alerts go out by Pushover and email."),
        E("Guides", "Admin > Guides", "Leadership", "Who the Guides are, their order and their hours.", "call volunteers."),
        E("Call requests queue", "Admin > Call requests", "Contacts area", "Every request, who it went to, whether it was answered, with resend and close. On a claimed request, \"Hand to\u2026\" passes the person to a different Guide, who is emailed their own link. Choosing and changing Guides (this, and the Guides page) is limited to the Owner and the Leadership accounts the Owner has ticked Guides for.", "call_requests."),
        E("Interest report", "Admin > Interest report", "Contacts area", "A report of everyone who used the interest forms and whether anyone reached them.", "interest_log."),
        E("Guide training pages", "/cep-training and /cep-letters", "Guides", "Training and sample letters for Guides.", ""),
        E("Volunteer helper sign-up", "/volunteer-helper/join", "Past volunteers", "A page where a volunteer joins the helper team.", "call volunteers."),
    ]),
    ("email", "Email and letters", "How we write to people.", [
        E("Trainee Correspondence", "Correspondence > Trainee Correspondence", "Leadership and Owner",
          "Pick a program session and open its trainee letters: confirmations and reminders, with a preview, a test copy to yourself and a tick-box send. Each person gets each letter once.",
          "session_letters_sent. Sending is off until SESSION_LETTERS_LIVE=1 is set."),
        E("Team Correspondence", "Correspondence > Team Correspondence", "Leadership and Owner",
          "Pick a session for the Facilitator, TA and Back-up TA letters, or write a free-form note to Facilitators, TA's, Support Team or Leadership (all sessions or one). Test copy to yourself first; typing SEND to confirm.",
          "cohort_staffing, staff, team_notes (sent notes). Sending is off until SESSION_LETTERS_LIVE=1 is set."),
        E("Edit letter wording", "Correspondence > Trainee or Team Correspondence > Letter wording > Edit wording", "Owner (everyone else can read the wording and suggest changes)",
          "Change the wording of any session letter (trainee confirmation, reminders, facilitator, TA and Back-up TA letters). Preview it, send yourself a test, then save. The new wording is used for every letter sent from then on, in every session. Each letter that is sent is stored exactly as it went out, and the green Sent date on a session's letters page opens that copy, so edits never change what was already sent. Reset returns a letter to the original wording.",
          "session_letter_text (the edits); session_letters_sent (who got what, with a copy of the letter). Letters sent before copies were kept show no copy."),
        E("All Letters", "Correspondence > All Letters", "Every login can view; only the Owner changes wording (Marketing items: Owner and Correspondence access)",
          "One page listing every letter that goes out, grouped by reason: people who ask to be called, trainees, team, Guides, testimonials, marketing. Each shows what triggers it, who gets it, and whether it is automated, by hand, or both. View shows the current letter; the Owner also gets Edit wording where the wording can be changed.",
          "Built from the letters in the program; edited wording in session_letter_text."),
        E("Letter history (version tracking)", "All Letters > Edit wording > History", "Leadership and Owner",
          "Every save of a letter is kept as a numbered version with who, when and an optional note. Read any older version or Restore it (restoring is itself saved as a new version). Applies to the Guide-call letters (curious, registration link, questionnaire link) and the session letters.",
          "letter_versions."),
        E("Suggest a change to a letter", "Correspondence > All Letters (logins) and the Guides' Letters we send page (no login)", "Anyone with a login, and Guides",
          "A button lets a volunteer send a suggested change for any letter. Only the Owner changes the wording of automated correspondence; suggestions go to the Owner by email and are listed under All Letters > Suggested changes, where each can be marked handled.",
          "letter_suggestions."),
        E("Accounting & Legal Correspondence", "Correspondence > Accounting & Legal", "Owner and anyone given Correspondence",
          "A free-form note to the Accounting & Legal logins, with a test copy first and SEND to confirm.", "staff, team_notes."),
        E("Marketing & Email Blasts", "Correspondence > Marketing & Email Blasts", "Owner and anyone given Correspondence",
          "Write a letter, choose the audience (a Data Source, program attendees, Guides, volunteers or the entire database), preview, send a test and send. Every blast includes an unsubscribe link.",
          "email_blasts and letters; sent through Brevo. See Brevo."),
        E("Excitement email and the long-form thank-you", "On a contact's record", "Contacts area", "Send the Excitement email, then the thank-you after someone completes the long form. The thank-you includes a testimonial invitation only for people who say they attended a Discovery training.", "contacts, testimonials."),
        E("Video call link and business plan", "On a contact's record", "Contacts area (business plan: Leadership)", "Send the video call link or the business plan to a contact.", ""),
        E("Brevo (email sender)", "Behind the scenes", "Owner", "All email goes out through Brevo from Kent Hafemann. Emails sent this way do not appear in Kent's own Sent folder, so invitations also BCC Kent.", "Settings in the hosting service."),
    ]),
    ("testimonials", "Testimonials", "Collecting and publishing what people say.", [
        E("Testimonials review", "Admin > Testimonials", "Leadership",
          "The pipeline for requests and stories: invitations sent, replies, editing, sending back for the person's approval, publishing, hiding and deleting. The stories on/off switch is at the top.",
          "testimonials, testimonial_requests, app_settings."),
        E("Invite someone", "Testimonials > Request", "Leadership", "Choose a contact, write a personal note in the letter box and send it by email, or get a text message to send yourself. Includes an option to add website links.", "Email through Brevo; BCC to Kent."),
        E("How a story gets published", "Testimonials", "Leadership", "Person submits, Leadership reviews and edits, sends back to the person for approval, and only after approval can it be published. Therapeutic words are flagged. Videos are limited to about 2 minutes.", "testimonials (videos stored in the database)."),
    ]),
    ("money", "Money and budgets", "", [
        E("Finance overview", "Admin > Finance > Finance overview", "Owner and Accounting & Legal", "Payments received and money summaries, with a CSV export.", "payments, donations."),
        E("Record payment", "On a session page", "Money access", "Record what a couple or person paid. The Art of Us amount starts at the program fee and one payment covers both partners.", "payments, enrollments."),
        E("Donations", "Admin > Finance > Donations", "Leadership or Donations area", "Every donation, with void.", "donations."),
        E("Budgets", "Admin > Finance > Budgets", "Owner and anyone given Budgets",
          "One budget per training, one for fixed and one-time expenses, and one for donations. Edit, add and delete lines. Download as Excel or PDF. The Owner can email a copy to selected leaders. Others can send a Request a budget change.",
          "budgets, budget_requests; Excel and PDF built from budget_model."),
    ]),
    ("access", "Team and access", "Who can see and do what.", [
        E("Roles", "Four login doors", "Owner decides", "Volunteer Team, Leadership, Accounting & Legal (view only) and Owner. Leadership sees confidential areas only after the Owner grants them. Only the Owner transfers ownership, changes access areas and assigns Accounting & Legal logins.", "staff, access_grants."),
        E("HUB Access", "HUB Access (main menu)", "Owner and Leadership", "Add people, reset passwords, link a login to a contact, deactivate and reactivate.", "staff."),
        E("Authorized users (access areas)", "From HUB Access", "Owner", "Hands out the fixed areas (Accounting, Marketing, Correspondence, Guides, Contacts, Donations, Contracts, Budgets and others) and each program's four headings.", "access_grants."),
        E("Website Leaders", "Admin > Website Leaders", "Owner and Leadership", "Controls who appears on the public team page.", "website_team."),
        E("Sponsor form and page", "Public page /sponsor (no login)", "Any volunteer", "A volunteer fills out one short form with their own details and the person they want to sponsor, and gives permission. We email them a letter (editable under Correspondence) asking them to complete their own long form and photo, and explaining the private web page they will get. That page (the same one a Guide uses) opens once their long form is complete, with a next-step card, checklist, one-tap letters, payment nudges and a place to log how it went. Sponsors are kept apart from the Guide groups.", "call_volunteers (SPONSOR), call_requests (source sponsor), call_notices."),
        E("Chat Room", "Main menu", "People given chat access", "Discussion topics and a live room for the team.", "chat tables."),
        E("Mission and Dashboard", "Main menu", "Everyone logged in", "The mission statement and the home screen with upcoming sessions.", ""),
    ]),
    ("owner", "Owner tools", "", [
        E("Database map", "Admin > Database map", "Owner", "A layered picture of how the database is organized, with live counts and a view of how site access is divided.", "Reads the live database."),
        E("Database Features (this guide)", "Admin > Database Features > How the site works", "Owner", "This page, with a PDF copy to share with an attorney, accountant or buyer. Kept current each time a feature is added.", "feature_guide.py."),
        E("Download for Claude", "Admin > Download for Claude", "Owner", "Packages the program's information so a new working session with Claude can pick up where the last one stopped.", ""),
    ]),
]


def _plain(s):
    return (s or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")


def build_pdf(program_name):
    from xml.sax.saxutils import escape
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch, topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                            title="Database Features", author=program_name)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=22, textColor=colors.HexColor("#1f6f8b"), spaceAfter=4)
    sub = ParagraphStyle("sub", parent=ss["Normal"], fontSize=10, textColor=colors.HexColor("#555555"), spaceAfter=14)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=15, textColor=colors.white, backColor=colors.HexColor("#1f6f8b"), borderPadding=(5, 6, 5, 6), spaceBefore=16, spaceAfter=8)
    intro = ParagraphStyle("intro", parent=ss["Italic"], fontSize=10, spaceAfter=6)
    nm = ParagraphStyle("nm", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=10.5, spaceAfter=2)
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=9.5, leading=12.5)
    lab = ParagraphStyle("lab", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#444444"))
    out = [Paragraph("Database Features: how the site works", h1),
           Paragraph(escape(_plain(program_name)) + " &middot; Updated " + escape(GUIDE_UPDATED) + " &middot; What each feature does, where to find it and who can use it", sub)]
    for key, title, blurb, entries in SECTIONS:
        out.append(Paragraph(escape(_plain(title)), h2))
        if blurb:
            out.append(Paragraph(escape(_plain(blurb)), intro))
        for e in entries:
            rows = [[Paragraph("Where", lab), Paragraph(escape(_plain(e["where"])), body)],
                    [Paragraph("Who", lab), Paragraph(escape(_plain(e["who"])), body)],
                    [Paragraph("What", lab), Paragraph(escape(_plain(e["what"])), body)]]
            if e["connects"]:
                rows.append([Paragraph("Connects to", lab), Paragraph(escape(_plain(e["connects"])), body)])
            t = Table(rows, colWidths=[0.95 * inch, 6.1 * inch])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                                   ("LINEBELOW", (0, -1), (-1, -1), 0.4, colors.HexColor("#d9e2ec"))]))
            out.append(KeepTogether([Paragraph(escape(_plain(e["name"])), nm), t, Spacer(1, 7)]))

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(0.7 * inch, 0.45 * inch, _plain(program_name) + " - Database Features")
        canvas.drawRightString(letter[0] - 0.7 * inch, 0.45 * inch, "Page %d" % d.page)
        canvas.restoreState()
    doc.build(out, onFirstPage=footer, onLaterPages=footer)
    buf.seek(0)
    return buf


def register(app, crm, owner_required, program_name):
    @crm.route("/feature-guide")
    @owner_required
    def feature_guide():
        return render_template("feature_guide.html", sections=SECTIONS, updated=GUIDE_UPDATED)

    @crm.route("/feature-guide.pdf")
    @owner_required
    def feature_guide_pdf():
        return send_file(build_pdf(program_name), mimetype="application/pdf", as_attachment=True, download_name="Database_Features.pdf")

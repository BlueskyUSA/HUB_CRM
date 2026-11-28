"""Plain-language purpose of every letter on the Correspondence page, shown on the Letter Guide.
Keyed by the letter's key (or slug), or by its name for entries that have neither."""

PURPOSE = {
    # Interested people
    "welcome": "A warm first thank-you from Kent, with a short story of why he and Pamela value the training, and an offer of a call. For people who chose \"Interested Party\" on the I'm Interested form.",
    "longform_followup": "Invites a past volunteer to fill in their profile so we can place them on the volunteer teams.",
    "longform_thankyou": "Thanks the person for finishing their profile, and offers the preliminary business plan.",
    "connect": "Confirms we received their message and that someone will reach out.",
    "excitement": "A short update that excitement about Discovery reopening is growing.",
    "plan": "Sends the preliminary business plan to someone who asked to see it.",
    "venue": "Tells people where the training is held and what the hotel stay and meals include.",
    # Contacts
    "profile_request": "Asks a contact to complete or update their profile. The same wording opens their profile page.",
    "testimonial_request": "Invites a former trainee or volunteer to share their experience.",
    "needs_request": "Asks session team members about food and physical needs before a session.",
    "video_call": "Sends a Google Meet link so a conversation can happen by video.",
    "site_invitation": "Invites a friend to look at the website while it is still private, with a personal link made just for them.",
    # Trainees
    "seminar_registration": "Gives the trainee their registration details for the training.",
    "seminar_registration_other": "Gives the trainee their registration details for the training.",
    "trainee_confirm": "Confirms the trainee's place in the training.",
    "trainee_confirm_other": "Confirms the trainee's place in the training.",
    "payment_reminder": "A friendly reminder to pay before arriving. It says payment cannot be taken at the check-in table.",
    "payment_reminder_other": "A friendly reminder to pay before arriving. It says payment cannot be taken at the check-in table.",
    "payment_received": "Thanks the trainee for paying and tells them we are excited to see them.",
    "payment_received_other": "Thanks the trainee for paying and tells them we are excited to see them.",
    "questionnaire_request": "Gives the trainee their private link to fill in the questionnaire.",
    "questionnaire_request_other": "Gives the trainee their private link to fill in the questionnaire.",
    "questionnaire_reminder": "A friendly nudge to finish the questionnaire.",
    "questionnaire_reminder_other": "A friendly nudge to finish the questionnaire.",
    "Questionnaire: The Art of Us": "The form itself, not a letter. Each partner fills it in on a private link.",
    "Questionnaire: The Beginning": "The form itself, not a letter. Each person fills it in on a private link.",
    "Questionnaire: other programs": "The form itself, not a letter. A short standard set of questions for the other programs.",
    "what_to_bring_aou": "Tells trainees what to pack and bring, a week before the training.",
    "what_to_bring": "Tells trainees what to pack and bring, a week before the training.",
    "completion": "Goes to trainees after the training ends.",
    "contract": "Congratulates people who completed the training and asks for the contract information we need.",
    # Team
    "facilitator_confirm": "Thanks and confirms a Facilitator for a session.",
    "ta_invitation": "Invites a person to serve as a TA. The button opens a private page where they answer Yes or No.",
    "ta_confirm": "Confirms a TA for a session.",
    "backup_confirm": "Thanks a back-up TA and confirms their place.",
    "Team notes": "Your own message to a team group. You write it each time.",
    "Welcome to a new login": "Gives a new team member their login link and temporary password. Also sent when a password is reset.",
    # Volunteers
    "guide_curious": "The first reply to a person who asked to be called, sent as soon as an Ambassador takes the request.",
    "guide_register": "Gives the person the registration link after the Ambassador has spoken with them.",
    "guide_questionnaire": "Gives the person their questionnaire link after they have reserved.",
    "guide_longform": "Asks the person to complete their profile after they have reserved.",
    "guide_payment": "Asks the person to make their payment.",
    "guide_payment_reminder": "A reminder, from the Ambassador, to someone who has reserved but not paid.",
    "New call request": "Alerts the Ambassadors that someone wants to be called, so one of them can say yes.",
    "Unclaimed request and call reminders": "Tells you and the Ambassador Team Captain that nobody claimed a request, and reminds an Ambassador to log a call.",
    "Milestone emails": "Tells an Ambassador when the person they talked with registers, pays, or is late paying.",
    "Sponsor a Friend (the public form page)": "The public page where a volunteer starts sponsoring someone. It is a page, not a letter.",
    "sponsor_welcome": "Welcomes a volunteer who submitted the Sponsor form and asks them to complete their profile.",
    "sponsor_page": "Thanks the sponsor once their contact form is complete and gives them their page.",
    "helper_welcome": "Welcomes a new volunteer to the helper team.",
    # Testimonials
    "Share your experience": "Invites a past trainee to share their story.",
    "A new testimonial is ready to review": "Tells Leadership a testimonial came in and is waiting for review.",
    "Please check your story before we share it": "Asks the person who wrote a testimonial to approve it before it is shared.",
    # Marketing / internal
    "Marketing & Email Blasts": "Announcements to your wider community, with test, SEND and unsubscribe safeguards.",
    "Budget emails and change requests": "Sends a budget, or a request to change one, to the people named on it.",
    "Accounting & Legal notes": "Your own note to the Accounting & Legal logins. You write it each time.",
}

JOURNEY = [
    ("Someone shows interest", "They fill in the \"I'm curious\" form (front page, program pages, Reserve page) or the I'm Interested form. Ambassadors get a call request. The person gets a reply, or the Welcome letter."),
    ("An Ambassador talks with them", "The Ambassador sends the registration link, then, after they reserve, the questionnaire, profile and payment links."),
    ("They register", "They receive their registration confirmation. The Ambassador is told they registered."),
    ("They pay", "The thank-you letter goes out when payment is recorded. If payment is late, the Ambassador is nudged every 7 days and decides whether to send a reminder."),
    ("Before the training", "Questionnaire request and reminder, then What to Bring a week before."),
    ("Check-in", "Greeters use the Check-in page. No letter goes out. Payment is not taken at the table."),
    ("After the training", "The After the training letter goes out, then the contract information request by hand."),
    ("The team", "Facilitators, TAs and back-up TAs each get their invitation or confirmation by hand from the session's letters page."),
]

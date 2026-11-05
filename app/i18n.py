"""English, French and Arabic (right to left).

The page text is written in English in the templates, as _("English text"). This module looks the
text up in the French or Arabic list and falls back to the English text when there is no entry, so
a missing translation can never break a page. The language is the visitor's explicit choice,
kept in the session, and only the three codes below are ever accepted.

Only the interface is translated. Descriptions of places, error messages from the server and the
admin area stay in English.
"""
import re

from flask import request, session

LANGS = {"en": ("English", "ltr"), "fr": ("Français", "ltr"), "ar": ("العربية", "rtl")}
DEFAULT_LANG = "en"
SHORT = {"en": "EN", "fr": "FR", "ar": "ع"}


def clean_lang(raw) -> str:
    return raw if isinstance(raw, str) and raw in LANGS else DEFAULT_LANG


def current_lang() -> str:
    if not request:
        return DEFAULT_LANG
    return clean_lang(session.get("lang"))


def lang_dir() -> str:
    return LANGS[current_lang()][1]


def translate(text: str, **values) -> str:
    """The text in the visitor's language; %(name)s placeholders are filled from values."""
    lang = current_lang()
    result = CATALOG.get(lang, {}).get(text, text)
    return result % values if values else result


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def translate_months(text: str) -> str:
    """"Mar to May, Sep to Nov" in the visitor's language."""
    if current_lang() == DEFAULT_LANG or not text:
        return text
    text = re.sub(r"\b(" + "|".join(_MONTHS) + r")\b", lambda m: translate(m.group(1)), text)
    return text.replace(" to ", " " + translate("to") + " ")


def long_date(value) -> str:
    """"Monday 09 November 2026" in the visitor's language."""
    return f"{translate(value.strftime('%A'))} {value.day:02d} {translate(value.strftime('%B'))} {value.year}"


def _pairs(*rows):
    return {en: (fr, ar) for en, fr, ar in rows}


ROWS = _pairs(
    # ---- header, footer, shared
    ("Skip to content", "Aller au contenu", "انتقل إلى المحتوى"),
    ("SecurePass home", "Accueil SecurePass", "الصفحة الرئيسية لـ SecurePass"),
    ("Main", "Principal", "القائمة الرئيسية"),
    ("Explore Flights", "Explorer les vols", "استكشاف الرحلات"),
    ("Countries", "Pays", "الدول"),
    ("Plan by month", "Planifier par mois", "خطّط حسب الشهر"),
    ("My Bookings", "Mes réservations", "حجوزاتي"),
    ("Admin", "Administration", "الإدارة"),
    ("Show prices in", "Afficher les prix en", "عرض الأسعار بـ"),
    ("Language", "Langue", "اللغة"),
    ("My account", "Mon compte", "حسابي"),
    ("Log out", "Se déconnecter", "تسجيل الخروج"),
    ("Log in", "Se connecter", "تسجيل الدخول"),
    ("Register", "S'inscrire", "إنشاء حساب"),
    ("Explore", "Explorer", "استكشف"),
    ("Account", "Compte", "الحساب"),
    ("Book with confidence. Fly with security.", "Réservez en confiance. Voyagez en sécurité.", "احجز بثقة. سافر بأمان."),
    ("Built secure", "Conçu pour la sécurité", "مصمَّم للأمان"),
    ("Protected accounts", "Comptes protégés", "حسابات محمية"),
    ("Safe bookings", "Réservations sûres", "حجوزات آمنة"),
    ("Audited security events", "Événements de sécurité audités", "أحداث أمنية مدقَّقة"),
    ("SecurePass is a final-year project. Demo data only: no real bookings or payments. Dinar and euro prices use fixed, indicative rates.",
     "SecurePass est un projet de fin d'études. Données de démonstration uniquement : aucune réservation ni aucun paiement réel. Les prix en dinars et en euros utilisent des taux fixes, indicatifs.",
     "SecurePass مشروع تخرّج. بيانات تجريبية فقط: لا حجوزات ولا مدفوعات حقيقية. أسعار الدينار واليورو بأسعار صرف ثابتة وتقريبية."),
    ("Fly safe.", "Bon voyage.", "رحلة سعيدة."),
    ("per passenger", "par passager", "للراكب"),
    ("From", "À partir de", "ابتداءً من"),
    ("Best", "Idéal", "الأفضل"),
    ("to", "à", "إلى"),
    ("All year", "Toute l'année", "طوال السنة"),
    # ---- home
    ("SecurePass: flights from Algeria, with every price in view",
     "SecurePass : des vols depuis l'Algérie, tous les prix affichés",
     "SecurePass: رحلات من الجزائر وكل الأسعار واضحة"),
    ("Where to next from Alger?", "Où aller depuis Alger ?", "إلى أين تسافر من الجزائر العاصمة؟"),
    ("Prices in dinars, seats you choose yourself, and an account that stays yours.",
     "Des prix en dinars, des sièges que vous choisissez vous-même et un compte qui reste le vôtre.",
     "أسعار بالدينار، ومقاعد تختارها بنفسك، وحساب يبقى ملكك."),
    ("cities", "villes", "مدينة"),
    ("countries", "pays", "دولة"),
    ("Prices in", "Prix en", "الأسعار بـ"),
    ("Two-step login available", "Connexion en deux étapes disponible", "تسجيل الدخول بخطوتين متاح"),
    ("Where to go this %(season)s", "Où partir : %(season)s", "إلى أين تسافر في فصل %(season)s"),
    ("Choose a season", "Choisissez une saison", "اختر فصلاً"),
    ("No countries are listed for this season yet.", "Aucun pays n'est encore proposé pour cette saison.", "لا توجد دول مقترحة لهذا الفصل بعد."),
    ("General travel guidance, not a weather forecast. Flight prices are the lowest fares from Alger.",
     "Conseils de voyage généraux, pas une prévision météo. Les prix sont les tarifs les plus bas depuis Alger.",
     "إرشادات سفر عامة وليست توقعات طقس. الأسعار هي أقل الأسعار من الجزائر العاصمة."),
    ("Top trips from %(city)s", "Meilleurs voyages depuis %(city)s", "أفضل الرحلات من %(city)s"),
    ("All countries", "Tous les pays", "كل الدول"),
    ("How booking works", "Comment fonctionne la réservation", "كيف يعمل الحجز"),
    ("Four clear steps from search to boarding pass, with nothing hidden.",
     "Quatre étapes claires, de la recherche à la carte d'embarquement, sans rien de caché.",
     "أربع خطوات واضحة من البحث إلى بطاقة الصعود، دون أي رسوم مخفية."),
    ("Search", "Rechercher", "ابحث"),
    ("Choose", "Choisir", "اختر"),
    ("Confirm", "Confirmer", "أكّد"),
    ("Manage", "Gérer", "أدِر"),
    ("Pick your airports, dates and passengers. Results come back quickly, with every price shown up front.",
     "Choisissez vos aéroports, vos dates et vos passagers. Les résultats arrivent vite, avec tous les prix affichés d'emblée.",
     "اختر المطارات والتواريخ والركاب. تصلك النتائج بسرعة مع عرض كل الأسعار مسبقاً."),
    ("Compare times, duration, price and seats left, then open the flight details.",
     "Comparez les horaires, la durée, le prix et les places restantes, puis ouvrez le détail du vol.",
     "قارن الأوقات والمدة والسعر والمقاعد المتبقية، ثم افتح تفاصيل الرحلة."),
    ("Choose your seats, review the total and finish with a demo payment. No card details are ever collected.",
     "Choisissez vos sièges, vérifiez le total et terminez par un paiement de démonstration. Aucune donnée de carte n'est collectée.",
     "اختر مقاعدك وراجع المجموع وأنهِ بدفع تجريبي. لا تُجمع أي بيانات بطاقة."),
    ("Find every booking in your account, each with a private reference code, and cancel from there.",
     "Retrouvez chaque réservation dans votre compte, avec son code de référence privé, et annulez-la depuis là.",
     "تجد كل حجوزاتك في حسابك، لكل منها رمز مرجعي خاص، ويمكنك الإلغاء من هناك."),
    ("Security you can see", "Une sécurité visible", "أمان ترونه بأعينكم"),
    ("The same care that goes into your trip goes into protecting your account and your bookings.",
     "Le même soin que pour votre voyage sert à protéger votre compte et vos réservations.",
     "نفس العناية التي نمنحها لرحلتك نمنحها لحماية حسابك وحجوزاتك."),
    ("Passwords are stored as salted hashes, wrong guesses lock the account for 15 minutes, and you can add a second step with an authenticator app.",
     "Les mots de passe sont stockés sous forme de hachages salés, les erreurs répétées bloquent le compte 15 minutes et vous pouvez ajouter une seconde étape avec une application d'authentification.",
     "تُخزَّن كلمات المرور مشفّرة بالملح، والمحاولات الخاطئة تقفل الحساب 15 دقيقة، ويمكنك إضافة خطوة ثانية بتطبيق مصادقة."),
    ("Every action is protected against forged requests, and seats are reserved in one step so none are sold twice.",
     "Chaque action est protégée contre les requêtes falsifiées, et les sièges sont réservés en une seule étape pour qu'aucun ne soit vendu deux fois.",
     "كل إجراء محمي من الطلبات المزوّرة، وتُحجز المقاعد في خطوة واحدة فلا يُباع مقعد مرتين."),
    ("Logins, bookings and denied access are written to an audit log that administrators can review.",
     "Les connexions, réservations et accès refusés sont consignés dans un journal d'audit que les administrateurs peuvent consulter.",
     "تُسجَّل عمليات الدخول والحجز ومحاولات الوصول المرفوضة في سجل تدقيق يراجعه المسؤولون."),
    # ---- search form
    ("Trip type", "Type de voyage", "نوع الرحلة"),
    ("One way", "Aller simple", "ذهاب فقط"),
    ("Round trip", "Aller-retour", "ذهاب وعودة"),
    ("Multi-city", "Multi-destinations", "وجهات متعددة"),
    ("Soon", "Bientôt", "قريباً"),
    ("Multi-city search is planned for a later version", "La recherche multi-destinations est prévue plus tard", "البحث متعدد الوجهات مخطّط لإصدار لاحق"),
    ("Origin", "Départ", "المغادرة من"),
    ("Destination", "Destination", "الوجهة"),
    ("Departure date", "Date de départ", "تاريخ المغادرة"),
    ("Return date", "Date de retour", "تاريخ العودة"),
    ("(optional)", "(facultatif)", "(اختياري)"),
    ("Passengers", "Passagers", "الركاب"),
    ("passenger", "passager", "راكب"),
    ("passengers", "passagers", "ركاب"),
    ("Search available flights", "Rechercher des vols", "ابحث عن الرحلات المتاحة"),
    ("Swap origin and destination", "Inverser départ et destination", "تبديل المغادرة والوجهة"),
    # ---- countries, plan
    ("%(n)s countries you can fly to. Open one to see its cities, the best time to go and the lowest fares from Alger.",
     "%(n)s pays où vous pouvez voyager. Ouvrez-en un pour voir ses villes, la meilleure période et les tarifs les plus bas depuis Alger.",
     "%(n)s دولة يمكنك السفر إليها. افتح أي دولة لترى مدنها وأفضل وقت للزيارة وأقل الأسعار من الجزائر العاصمة."),
    ("Where to go in %(month)s", "Où partir en %(month)s", "إلى أين تسافر في %(month)s"),
    ("Pick a month and, if you like, the kind of trip. General travel guidance, not a weather forecast.",
     "Choisissez un mois et, si vous le souhaitez, le type de voyage. Conseils généraux, pas une prévision météo.",
     "اختر شهراً ونوع الرحلة إن أردت. إرشادات سفر عامة وليست توقعات طقس."),
    ("Choose a month", "Choisissez un mois", "اختر شهراً"),
    ("Choose a kind of trip", "Choisissez un type de voyage", "اختر نوع الرحلة"),
    ("Any trip", "Tous les voyages", "أي رحلة"),
    ("Nothing matches %(month)s with that kind of trip. Try another month or choose \"Any trip\".",
     "Rien ne correspond à %(month)s pour ce type de voyage. Essayez un autre mois ou choisissez « Tous les voyages ».",
     "لا شيء يناسب %(month)s لهذا النوع من الرحلات. جرّب شهراً آخر أو اختر «أي رحلة»."),
    ("Beach", "Plage", "شاطئ"), ("City break", "Séjour urbain", "رحلة مدينة"), ("Culture", "Culture", "ثقافة"),
    ("Nature", "Nature", "طبيعة"), ("Desert", "Désert", "صحراء"),
    ("Best time to go", "Meilleure période", "أفضل وقت للزيارة"),
    ("Good for", "Idéal pour", "مناسب لـ"),
    ("General travel guidance, not a weather forecast.", "Conseils de voyage généraux, pas une prévision météo.", "إرشادات سفر عامة وليست توقعات طقس."),
    ("Cities you can fly to", "Villes où vous pouvez voyager", "مدن يمكنك السفر إليها"),
    ("More places for this month", "Plus de destinations pour ce mois", "المزيد من الوجهات لهذا الشهر"),
    # ---- results
    ("Search flights", "Rechercher des vols", "البحث عن رحلات"),
    ("Find your flight", "Trouvez votre vol", "اعثر على رحلتك"),
    ("Please check your search:", "Veuillez vérifier votre recherche :", "يرجى مراجعة بحثك:"),
    ("Filter and sort results", "Filtrer et trier les résultats", "تصفية النتائج وترتيبها"),
    ("Filters", "Filtres", "عوامل التصفية"),
    ("Sort by", "Trier par", "ترتيب حسب"),
    ("Departure time", "Heure de départ", "وقت المغادرة"),
    ("Lowest price", "Prix le plus bas", "الأقل سعراً"),
    ("Shortest duration", "Durée la plus courte", "الأقصر مدة"),
    ("Max price", "Prix maximum", "أعلى سعر"),
    ("Morning", "Matin", "صباحاً"), ("Afternoon", "Après-midi", "بعد الظهر"),
    ("Evening", "Soir", "مساءً"), ("Night", "Nuit", "ليلاً"),
    ("5am to 12pm", "5 h à 12 h", "من 5 ص إلى 12 ظ"), ("12pm to 6pm", "12 h à 18 h", "من 12 ظ إلى 6 م"),
    ("6pm to 10pm", "18 h à 22 h", "من 6 م إلى 10 م"), ("10pm to 5am", "22 h à 5 h", "من 10 م إلى 5 ص"),
    ("Airlines", "Compagnies", "شركات الطيران"),
    ("Reset filters", "Réinitialiser les filtres", "إعادة ضبط التصفية"),
    ("Outbound", "Aller", "الذهاب"), ("Return", "Retour", "العودة"),
    ("%(a)s to %(b)s", "%(a)s vers %(b)s", "من %(a)s إلى %(b)s"),
    ("%(n)s seats left", "%(n)s places restantes", "%(n)s مقعد متبقٍ"),
    ("Operated by %(name)s", "Assuré par %(name)s", "تشغّلها %(name)s"),
    ("Non-stop", "Direct", "بدون توقف"), ("Almost full", "Presque complet", "شبه ممتلئة"),
    ("View details", "Voir le détail", "عرض التفاصيل"),
    ("No flights match this search. Try another date or fewer passengers.",
     "Aucun vol ne correspond. Essayez une autre date ou moins de passagers.",
     "لا توجد رحلات مطابقة. جرّب تاريخاً آخر أو عدد ركاب أقل."),
    ("Enter your airports and dates above to see available flights.",
     "Saisissez vos aéroports et vos dates ci-dessus pour voir les vols disponibles.",
     "أدخل المطارات والتواريخ أعلاه لعرض الرحلات المتاحة."),
    # ---- steps
    ("Booking progress", "Progression de la réservation", "مراحل الحجز"),
    ("Choose flight", "Choisir le vol", "اختيار الرحلة"),
    ("Review & pay", "Vérifier et payer", "المراجعة والدفع"),
    ("Confirmation", "Confirmation", "التأكيد"),
    # ---- flight detail, checkout
    ("Back to search", "Retour à la recherche", "العودة إلى البحث"),
    ("Back to flight", "Retour au vol", "العودة إلى الرحلة"),
    ("Flight", "Vol", "الرحلة"),
    ("Price", "Prix", "السعر"),
    ("Seats left", "Places restantes", "المقاعد المتبقية"),
    ("%(price)s per passenger", "%(price)s par passager", "%(price)s للراكب"),
    ("%(time)s (local time)", "%(time)s (heure locale)", "%(time)s (بالتوقيت المحلي)"),
    ("You need an account to reserve seats.", "Il faut un compte pour réserver des sièges.", "تحتاج إلى حساب لحجز المقاعد."),
    ("Log in to book", "Connectez-vous pour réserver", "سجّل الدخول للحجز"),
    ("This flight has already departed.", "Ce vol est déjà parti.", "غادرت هذه الرحلة بالفعل."),
    ("This flight is sold out.", "Ce vol est complet.", "نفدت مقاعد هذه الرحلة."),
    ("Continue to booking", "Continuer vers la réservation", "المتابعة إلى الحجز"),
    ("Confirm your booking", "Confirmez votre réservation", "أكّد حجزك"),
    ("Price per passenger", "Prix par passager", "السعر للراكب"),
    ("Total", "Total", "المجموع"),
    ("Passenger details", "Informations des passagers", "بيانات الركاب"),
    ("Enter each name as it appears on the travel document. Names only: no passport or card details are collected.",
     "Saisissez chaque nom tel qu'il figure sur le document de voyage. Noms uniquement : aucune donnée de passeport ou de carte n'est collectée.",
     "أدخل كل اسم كما يظهر في وثيقة السفر. الأسماء فقط: لا تُجمع بيانات جواز أو بطاقة."),
    ("Passenger %(n)s", "Passager %(n)s", "الراكب %(n)s"),
    ("Lead", "Principal", "الرئيسي"),
    ("First name", "Prénom", "الاسم الأول"), ("Last name", "Nom", "اسم العائلة"),
    ("Please check the passenger names below.", "Veuillez vérifier les noms des passagers ci-dessous.", "يرجى مراجعة أسماء الركاب أدناه."),
    ("Payment method", "Mode de paiement", "طريقة الدفع"),
    ("Bank card", "Carte bancaire", "بطاقة مصرفية"),
    ("CIB card", "Carte CIB", "بطاقة CIB"),
    ("BaridiMob", "BaridiMob", "بريدي موب"),
    ("Cash at an agency", "Espèces en agence", "نقداً في وكالة"),
    ("Visa or Mastercard. Demo only: no card number is asked for.", "Visa ou Mastercard. Démonstration : aucun numéro de carte n'est demandé.", "فيزا أو ماستركارد. تجريبي فقط: لا يُطلب رقم البطاقة."),
    ("Algerian interbank card. Demo only: no card number is asked for.", "Carte interbancaire algérienne. Démonstration : aucun numéro de carte n'est demandé.", "بطاقة الدفع البنكية الجزائرية. تجريبي فقط: لا يُطلب رقم البطاقة."),
    ("Pay from the BaridiMob app. Demo only: nothing is sent to the app.", "Payez depuis l'application BaridiMob. Démonstration : rien n'est envoyé à l'application.", "ادفع من تطبيق بريدي موب. تجريبي فقط: لا يُرسل شيء إلى التطبيق."),
    ("Pay in cash at a partner agency before departure. Demo only.", "Payez en espèces dans une agence partenaire avant le départ. Démonstration.", "ادفع نقداً في وكالة شريكة قبل المغادرة. تجريبي فقط."),
    ("Demo payment.", "Paiement de démonstration.", "دفع تجريبي."),
    ("No real payment is taken and no card details are collected.", "Aucun paiement réel n'est effectué et aucune donnée de carte n'est collectée.", "لا يُسحب أي مبلغ حقيقي ولا تُجمع بيانات بطاقة."),
    ("Pay %(total)s (demo) and book", "Payer %(total)s (démo) et réserver", "ادفع %(total)s (تجريبي) واحجز"),
    ("Search other flights", "Chercher d'autres vols", "ابحث عن رحلات أخرى"),
    # ---- bookings
    ("My bookings", "Mes réservations", "حجوزاتي"),
    ("You have no bookings yet.", "Vous n'avez encore aucune réservation.", "ليس لديك أي حجوزات بعد."),
    ("Find a flight", "Trouver un vol", "ابحث عن رحلة"),
    ("View", "Voir", "عرض"),
    ("Reference", "Référence", "المرجع"),
    ("All my bookings", "Toutes mes réservations", "كل حجوزاتي"),
    ("Confirmed", "Confirmée", "مؤكَّد"), ("Cancelled", "Annulée", "ملغى"),
    ("Total (demo)", "Total (démo)", "المجموع (تجريبي)"),
    ("Payment (demo)", "Paiement (démo)", "الدفع (تجريبي)"),
    ("Booked on", "Réservé le", "تاريخ الحجز"),
    ("View e-ticket", "Voir le billet électronique", "عرض التذكرة الإلكترونية"),
    ("Choose seats", "Choisir les sièges", "اختيار المقاعد"), ("Change seats", "Changer les sièges", "تغيير المقاعد"),
    ("Cancel this booking", "Annuler cette réservation", "إلغاء هذا الحجز"),
    ("Seat %(label)s", "Siège %(label)s", "المقعد %(label)s"),
    ("No seat chosen", "Aucun siège choisi", "لم يُختر مقعد"),
    ("Your e-ticket", "Votre billet électronique", "تذكرتك الإلكترونية"),
    ("Back to booking", "Retour à la réservation", "العودة إلى الحجز"),
    ("SecurePass · Boarding pass (demo)", "SecurePass · Carte d'embarquement (démo)", "SecurePass · بطاقة صعود (تجريبية)"),
    ("Date", "Date", "التاريخ"), ("Payment", "Paiement", "الدفع"),
    ("Booking reference", "Référence de réservation", "مرجع الحجز"),
    ("Seat not chosen", "Siège non choisi", "لم يُختر المقعد"),
    ("Print this ticket", "Imprimer ce billet", "اطبع هذه التذكرة"),
    ("Demo ticket from a final-year project. It is not valid for travel.", "Billet de démonstration d'un projet de fin d'études. Il n'est pas valable pour voyager.", "تذكرة تجريبية من مشروع تخرّج. غير صالحة للسفر."),
    # ---- auth
    ("Welcome back.", "Content de vous revoir.", "مرحباً بعودتك."),
    ("Email", "E-mail", "البريد الإلكتروني"),
    ("Password", "Mot de passe", "كلمة المرور"),
    ("Forgot your password?", "Mot de passe oublié ?", "هل نسيت كلمة المرور؟"),
    ("New here?", "Nouveau ici ?", "جديد هنا؟"),
    ("Create an account", "Créer un compte", "إنشاء حساب"),
    ("Book flights and manage your trips securely.", "Réservez des vols et gérez vos voyages en toute sécurité.", "احجز الرحلات وأدِر سفراتك بأمان."),
    ("At least 10 characters, with a letter and a number.", "Au moins 10 caractères, avec une lettre et un chiffre.", "10 أحرف على الأقل، مع حرف ورقم."),
    ("Confirm password", "Confirmer le mot de passe", "تأكيد كلمة المرور"),
    ("Create account", "Créer le compte", "إنشاء الحساب"),
    ("Already registered?", "Déjà inscrit ?", "لديك حساب؟"),
    # ---- seasons, months, days
    ("Winter", "Hiver", "الشتاء"), ("Spring", "Printemps", "الربيع"), ("Summer", "Été", "الصيف"), ("Autumn", "Automne", "الخريف"),
    ("winter", "hiver", "الشتاء"), ("spring", "printemps", "الربيع"), ("summer", "été", "الصيف"), ("autumn", "automne", "الخريف"),
    ("January", "janvier", "يناير"), ("February", "février", "فبراير"), ("March", "mars", "مارس"), ("April", "avril", "أبريل"),
    ("May", "mai", "مايو"), ("June", "juin", "يونيو"), ("July", "juillet", "يوليو"), ("August", "août", "أغسطس"),
    ("September", "septembre", "سبتمبر"), ("October", "octobre", "أكتوبر"), ("November", "novembre", "نوفمبر"), ("December", "décembre", "ديسمبر"),
    ("Jan", "janv.", "يناير"), ("Feb", "févr.", "فبراير"), ("Mar", "mars", "مارس"), ("Apr", "avr.", "أبريل"),
    ("Jun", "juin", "يونيو"), ("Jul", "juil.", "يوليو"), ("Aug", "août", "أغسطس"), ("Sep", "sept.", "سبتمبر"),
    ("Oct", "oct.", "أكتوبر"), ("Nov", "nov.", "نوفمبر"), ("Dec", "déc.", "ديسمبر"),
    ("Monday", "lundi", "الاثنين"), ("Tuesday", "mardi", "الثلاثاء"), ("Wednesday", "mercredi", "الأربعاء"),
    ("Thursday", "jeudi", "الخميس"), ("Friday", "vendredi", "الجمعة"), ("Saturday", "samedi", "السبت"), ("Sunday", "dimanche", "الأحد"),
    # ---- cities
    ("Tokyo", "Tokyo", "طوكيو"), ("Santorini", "Santorin", "سانتوريني"), ("Serengeti", "Serengeti", "سيرينجيتي"),
    ("New York", "New York", "نيويورك"), ("London", "Londres", "لندن"), ("Paris", "Paris", "باريس"),
    ("Dubai", "Dubaï", "دبي"), ("Rome", "Rome", "روما"), ("Istanbul", "Istanbul", "إسطنبول"), ("Barcelona", "Barcelone", "برشلونة"),
    ("Alger", "Alger", "الجزائر العاصمة"), ("Oran", "Oran", "وهران"), ("Constantine", "Constantine", "قسنطينة"),
    ("Annaba", "Annaba", "عنابة"), ("Tlemcen", "Tlemcen", "تلمسان"), ("Béjaïa", "Béjaïa", "بجاية"),
    ("Ghardaïa", "Ghardaïa", "غرداية"), ("Tamanrasset", "Tamanrasset", "تمنراست"), ("Tunis", "Tunis", "تونس العاصمة"),
    ("Casablanca", "Casablanca", "الدار البيضاء"), ("Cairo", "Le Caire", "القاهرة"), ("Jeddah", "Djeddah", "جدة"),
    ("Doha", "Doha", "الدوحة"), ("Madrid", "Madrid", "مدريد"), ("Marseille", "Marseille", "مرسيليا"),
    ("Montréal", "Montréal", "مونتريال"), ("Kuala Lumpur", "Kuala Lumpur", "كوالالمبور"), ("Bali", "Bali", "بالي"),
    # ---- countries
    ("Algeria", "Algérie", "الجزائر"), ("Tunisia", "Tunisie", "تونس"), ("Morocco", "Maroc", "المغرب"),
    ("Egypt", "Égypte", "مصر"), ("Saudi Arabia", "Arabie saoudite", "السعودية"), ("Qatar", "Qatar", "قطر"),
    ("United Arab Emirates", "Émirats arabes unis", "الإمارات العربية المتحدة"), ("Turkey", "Turquie", "تركيا"),
    ("Greece", "Grèce", "اليونان"), ("Italy", "Italie", "إيطاليا"), ("France", "France", "فرنسا"), ("Spain", "Espagne", "إسبانيا"),
    ("United Kingdom", "Royaume-Uni", "المملكة المتحدة"), ("United States", "États-Unis", "الولايات المتحدة"),
    ("Canada", "Canada", "كندا"), ("Japan", "Japon", "اليابان"), ("Malaysia", "Malaisie", "ماليزيا"),
    ("Indonesia", "Indonésie", "إندونيسيا"), ("Tanzania", "Tanzanie", "تنزانيا"),
)

CATALOG = {
    "en": {},
    "fr": {en: fr for en, (fr, ar) in ROWS.items()},
    "ar": {en: ar for en, (fr, ar) in ROWS.items()},
}

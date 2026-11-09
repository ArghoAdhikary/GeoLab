"""Language of the program: English (default) or Bangla (বাংলা).

The program is written in English; when Bangla is chosen (Edit > Preferences > Language), every window
is translated as it opens: menus, buttons, labels, tabs and titles whose text is in the table below.
Numbers, units and names entered by the user are never changed.
"""
from __future__ import annotations

LANGUAGES = {"en": "English", "bn": "বাংলা (Bangla)"}

BN = {
    # menus
    "File": "ফাইল", "Edit": "সম্পাদনা", "View": "দেখুন", "Define": "নির্ধারণ", "Draw": "আঁকুন",
    "Sketch": "স্কেচ", "Modify": "পরিবর্তন", "Window": "উইন্ডো", "Help": "সাহায্য", "Tools": "টুলস",
    "Design": "ডিজাইন", "Theme": "থিম", "Export": "এক্সপোর্ট", "Recent Files": "সাম্প্রতিক ফাইল",
    "Open Example": "উদাহরণ খুলুন", "New by Analysis Type": "বিশ্লেষণের ধরন অনুযায়ী নতুন",
    "Add Analysis": "বিশ্লেষণ যোগ করুন", "Add Child Analysis": "চাইল্ড বিশ্লেষণ যোগ করুন",
    "Add Child Analysis (uses the selected analysis)": "চাইল্ড বিশ্লেষণ যোগ করুন (নির্বাচিত বিশ্লেষণ ব্যবহার করে)",
    # file
    "New Project": "নতুন প্রজেক্ট", "New Quick Slope": "নতুন কুইক স্লোপ", "Open": "খুলুন", "Save": "সংরক্ষণ",
    "Save As": "অন্য নামে সংরক্ষণ", "Export PDF": "PDF এক্সপোর্ট", "Export Image (PNG)": "ছবি এক্সপোর্ট (PNG)",
    "Export Results (CSV)": "ফলাফল এক্সপোর্ট (CSV)", "Export Project (JSON)": "প্রজেক্ট এক্সপোর্ট (JSON)",
    "Export GeoStudio Project (.gsz)": "GeoStudio প্রজেক্ট এক্সপোর্ট (.gsz)",
    "Import Region Points (CSV)": "রিজিয়নের পয়েন্ট ইমপোর্ট (CSV)", "Print": "প্রিন্ট",
    "Delete All Results": "সব ফলাফল মুছুন", "Exit": "বন্ধ করুন",
    # edit / view
    "Undo": "আনডু", "Redo": "রিডু", "Copy Image": "ছবি কপি", "Go to Coordinate": "স্থানাঙ্কে যান",
    "Preferences": "পছন্দসমূহ", "Definition": "সংজ্ঞা", "Results": "ফলাফল", "Page Layout": "পৃষ্ঠা বিন্যাস",
    "Zoom to Fit": "পুরোটা দেখুন", "Zoom In": "জুম ইন", "Zoom Out": "জুম আউট", "Show Grid": "গ্রিড দেখান",
    "Snap to Grid": "গ্রিডে আটকান", "Show Mesh": "মেশ দেখান", "Show Slices": "স্লাইস দেখান",
    "Show Trial Slip Surfaces": "পরীক্ষামূলক স্লিপ সারফেস দেখান", "Show Flow Vectors": "প্রবাহের দিক দেখান",
    "Show Axes": "অক্ষ দেখান", "Show Deformed Mesh": "বিকৃত মেশ দেখান", "Show Yielded Zones": "ইল্ড অঞ্চল দেখান",
    "Report": "রিপোর্ট", "Slice Information": "স্লাইসের তথ্য", "Graph": "গ্রাফ", "Show Step Guide": "ধাপের গাইড দেখান",
    # define
    "Project Properties": "প্রজেক্টের বৈশিষ্ট্য", "Analyses": "বিশ্লেষণসমূহ", "Materials": "মাটির বৈশিষ্ট্য",
    "Delete Analysis": "বিশ্লেষণ মুছুন", "Boundary Conditions": "সীমানা শর্ত",
    "Piezometric Line Points": "পানির স্তরের রেখার পয়েন্ট", "Loads": "লোড", "Reinforcement": "রিইনফোর্সমেন্ট",
    "Flux Sections": "ফ্লাক্স সেকশন", "Structures (walls, anchors, geogrids)": "স্ট্রাকচার (দেয়াল, অ্যাঙ্কর, জিওগ্রিড)",
    "Slope stability (limit equilibrium)": "ঢালের স্থিতিশীলতা (লিমিট ইকুইলিব্রিয়াম)",
    "Seepage (groundwater flow)": "সিপেজ (ভূগর্ভস্থ পানির প্রবাহ)", "Stress-deformation": "স্ট্রেস-বিকৃতি",
    "Dynamic (earthquake)": "ডাইনামিক (ভূমিকম্প)", "Thermal (heat transfer, freezing)": "তাপীয় (তাপ পরিবহন, জমাট)",
    "Contaminant transport": "দূষক পরিবহন", "Air flow": "বায়ু প্রবাহ",
    # draw
    "Select": "নির্বাচন", "Regions": "রিজিয়ন (মাটির স্তর)", "Piezometric Line": "পানির স্তর রেখা",
    "Point Loads": "বিন্দু লোড", "Surcharge Loads": "সারচার্জ লোড",
    "Slip Surface Entry and Exit": "স্লিপ সারফেসের শুরু ও শেষ", "Slip Surface Grid": "স্লিপ সারফেস গ্রিড",
    "Structures (wall, anchor, geogrid)": "স্ট্রাকচার (দেয়াল, অ্যাঙ্কর, জিওগ্রিড)", "Sketch Text": "লেখা",
    "Pan": "সরান", "Slip Surface Entry and Exit Range": "স্লিপ সারফেসের শুরু ও শেষের সীমা",
    "Edit Region Points": "রিজিয়নের পয়েন্ট সম্পাদনা", "Delete Selected Region": "নির্বাচিত রিজিয়ন মুছুন",
    # window / solve
    "Solve Manager": "সমাধান ব্যবস্থাপক", "Verify": "যাচাই", "Solve Analysis": "সমাধান করুন",
    "Solve All": "সব সমাধান করুন", "Stop": "থামুন", "Reset Window Layout": "উইন্ডো বিন্যাস রিসেট",
    "Start Page": "শুরুর পাতা", "Project Explorer": "প্রজেক্ট এক্সপ্লোরার", "Properties": "বৈশিষ্ট্য",
    # help
    "Quick Guide": "দ্রুত গাইড", "User Manual": "ব্যবহারকারীর ম্যানুয়াল", "Tutorials": "টিউটোরিয়াল",
    "User Manual (PDF)": "ব্যবহারকারীর ম্যানুয়াল (PDF)", "Example Files Folder": "উদাহরণ ফাইলের ফোল্ডার",
    "AI Assistant Chat": "AI সহকারীর সাথে চ্যাট", "AI Slope Builder": "AI দিয়ে ঢাল তৈরি", "About": "সম্পর্কে",
    "Bangla Getting Started": "বাংলায় শুরু করার গাইড",
    # tools / design (new in 2.10)
    "Back-Analysis (from a failure)": "ব্যাক-অ্যানালাইসিস (ধসে পড়া ঢাল থেকে)",
    "Calibrate k from Piezometers": "পিজোমিটার থেকে k নির্ণয়", "Design Optimizer": "ডিজাইন অপটিমাইজার",
    "What-If Sliders": "কী-হলে স্লাইডার", "Design Code Check": "ডিজাইন কোড যাচাই",
    "Design Code Settings": "ডিজাইন কোড সেটিংস", "Liquefaction Check (SPT / CPT)": "তরলীকরণ যাচাই (SPT / CPT)",
    "Import Boreholes / CPT": "বোরহোল / CPT ইমপোর্ট", "Rainfall from Weather Data": "আবহাওয়ার তথ্য থেকে বৃষ্টিপাত",
    "Monitoring Data": "মনিটরিং তথ্য", "Model from Photo or Sketch (AI)": "ছবি বা স্কেচ থেকে মডেল (AI)",
    "Design Report (Word / PDF)": "ডিজাইন রিপোর্ট (Word / PDF)", "Python Console": "পাইথন কনসোল",
    "New River Bank": "নতুন নদীর পাড়", "New Flood Embankment": "নতুন বন্যা বাঁধ",
    # common buttons and labels
    "OK": "ঠিক আছে", "Cancel": "বাতিল", "Close": "বন্ধ", "Apply": "প্রয়োগ", "Run": "চালান", "Help ": "সাহায্য ",
    "Browse": "খুঁজুন", "Yes": "হ্যাঁ", "No": "না", "Add": "যোগ", "Remove": "সরান", "Delete": "মুছুন",
    "Solve now": "এখনই সমাধান করুন", "Target factor of safety": "লক্ষ্য নিরাপত্তা গুণক",
    "Factor of safety": "নিরাপত্তা গুণক (FoS)", "Material": "মাটি", "Analysis": "বিশ্লেষণ",
    "Design code": "ডিজাইন কোড", "Water table depth": "পানির স্তরের গভীরতা", "Earthquake magnitude": "ভূমিকম্পের মাত্রা",
    "Peak ground acceleration (g)": "সর্বোচ্চ ভূমি ত্বরণ (g)", "Use in the model": "মডেলে ব্যবহার করুন",
    "Open in GeoLab": "GeoLab-এ খুলুন", "Save Word": "Word সংরক্ষণ", "Save PDF": "PDF সংরক্ষণ",
    "Get the weather data": "আবহাওয়ার তথ্য আনুন", "Language": "ভাষা",
    # step guide
    "Draw the ground": "মাটি আঁকুন", "Soil properties": "মাটির বৈশিষ্ট্য", "Water table (optional)": "পানির স্তর (ঐচ্ছিক)",
    "Where it can slide": "কোথায় পিছলাতে পারে", "Supports and loads": "সাপোর্ট ও লোড",
    "Stages and structures (optional)": "ধাপ ও স্ট্রাকচার (ঐচ্ছিক)", "Solve": "সমাধান",
    "See the results": "ফলাফল দেখুন", "Next": "পরের ধাপ", "Done": "শেষ", "Hide guide": "গাইড লুকান",
    "Material": "মাটি", "Contour": "কনট্যুর", "Time": "সময়",
    "Click the corners of each soil layer on the drawing; click the first point again to close it. "
    "Or start from File > New Quick Slope.":
        "ছবিতে প্রতিটি মাটির স্তরের কোণগুলোতে ক্লিক করুন; বন্ধ করতে প্রথম পয়েন্টে আবার ক্লিক করুন। "
        "অথবা ফাইল > নতুন কুইক স্লোপ দিয়ে শুরু করুন।",
    "Open Materials and enter the strength (c', phi') and unit weight of each soil, then use "
    "Draw > Materials to click each region with its soil.":
        "মাটির বৈশিষ্ট্য খুলে প্রতিটি মাটির শক্তি (c', phi') ও একক ওজন দিন, তারপর আঁকুন > মাটির বৈশিষ্ট্য দিয়ে "
        "প্রতিটি রিজিয়নে তার মাটি ক্লিক করুন।",
    "If there is groundwater, draw the water table from left to right and press Enter. "
    "If the slope is dry you can skip this.":
        "ভূগর্ভস্থ পানি থাকলে বাম থেকে ডানে পানির স্তর আঁকুন এবং Enter চাপুন। ঢাল শুকনো হলে এটি বাদ দিতে পারেন।",
    "Tell GeoLab where slip surfaces may start (crest) and end (toe): Draw > Slip Surface Entry "
    "and Exit, or press Auto in the analysis settings.":
        "স্লিপ সারফেস কোথায় শুরু (চূড়া) ও শেষ (পাদদেশ) হতে পারে তা বলুন: আঁকুন > স্লিপ সারফেসের শুরু ও শেষ, "
        "অথবা বিশ্লেষণের সেটিংসে Auto চাপুন।",
    "Press Solve (F5). The Solve Manager at the bottom shows progress.":
        "সমাধান (F5) চাপুন। নিচের সমাধান ব্যবস্থাপকে অগ্রগতি দেখা যাবে।",
    "Switch to Results to see the factor of safety, contours and graphs. View > Report gives "
    "everything as text.":
        "নিরাপত্তা গুণক, কনট্যুর ও গ্রাফ দেখতে ফলাফলে যান। দেখুন > রিপোর্ট সবকিছু লেখা আকারে দেয়।",
    # 2.11: appearance, autosave, backup
    "Save As GeoStudio (.gsz)": "GeoStudio (.gsz) হিসেবে সংরক্ষণ", "Export as PDF": "PDF হিসেবে এক্সপোর্ট",
    "Recover Autosaved Project": "অটোসেভ করা প্রজেক্ট ফেরত আনুন",
    "Back Up to Cloud Drive Now": "এখনই ক্লাউড ড্রাইভে ব্যাকআপ",
    "Interface Style": "ইন্টারফেসের ধরন", "Colour Scheme": "রঙের স্কিম",
    "Customise Colours and Fonts": "রং ও ফন্ট নিজের মতো করুন",
    "Appearance": "চেহারা", "Advanced Colours & Fonts": "উন্নত রং ও ফন্ট", "Files & Backup": "ফাইল ও ব্যাকআপ",
    "AI Assistant": "AI সহকারী", "Autosave": "অটোসেভ", "Add Font...": "ফন্ট যোগ করুন...",
    "Save Theme...": "থিম সংরক্ষণ...", "Load Theme...": "থিম খুলুন...", "Reset All": "সব আগের মতো",
    "Reset": "আগের মতো", "Back Up Now": "এখনই ব্যাকআপ", "Open Backup Folder": "ব্যাকআপ ফোল্ডার খুলুন",
    "Interface style and colours": "ইন্টারফেসের ধরন ও রং", "Interface style": "ইন্টারফেসের ধরন",
    "Colour scheme": "রঙের স্কিম", "Accent colour": "প্রধান রং", "Interface font": "ইন্টারফেসের ফন্ট",
    "Your fonts": "আপনার ফন্ট", "Language": "ভাষা",
    "Save my work automatically (on by default)": "আমার কাজ নিজে থেকে সংরক্ষণ করুন (শুরু থেকেই চালু)",
    "Back up a dated copy of the project to a cloud drive": "প্রজেক্টের তারিখসহ কপি ক্লাউড ড্রাইভে রাখুন",
    # 2.12
    "Cross-Section from Map": "ম্যাপ থেকে সেকশন", "Landslide Early Warning": "ভূমিধস আগাম সতর্কতা",
    "Probabilistic Analysis and Sensitivity": "সম্ভাব্যতা বিশ্লেষণ ও সংবেদনশীলতা",
    "Foundations and Retaining Walls": "ফাউন্ডেশন ও রিটেইনিং ওয়াল", "Strength from Lab Tests": "ল্যাব টেস্ট থেকে শক্তি",
    "Estimate SWCC and k from Grain Size": "দানার আকার থেকে SWCC ও k", "Quantities and Cost": "পরিমাণ ও খরচ",
    "Compare Design Options": "ডিজাইন বিকল্পের তুলনা", "Import AutoCAD DXF": "AutoCAD DXF ইমপোর্ট",
    "Export AutoCAD DXF": "AutoCAD DXF এক্সপোর্ট", "Command Palette": "কমান্ড প্যালেট",
    "Keyboard Shortcuts and My Toolbar": "কি-বোর্ড শর্টকাট ও আমার টুলবার", "Version History": "ভার্সন ইতিহাস",
    "New Tab": "নতুন ট্যাব", "Open in New Tab": "নতুন ট্যাবে খুলুন", "Close Tab": "ট্যাব বন্ধ",
    "Check for Updates": "আপডেট খুঁজুন", "Share Report (HTML to Cloud Drive)": "রিপোর্ট শেয়ার (ক্লাউড ড্রাইভে HTML)",
    "History": "ইতিহাস", "Get Ground Levels": "মাটির উচ্চতা আনুন", "Make the Model": "মডেল তৈরি করুন",
    "Check Now": "এখনই দেখুন", "Calculate": "হিসাব করুন", "Fit": "ফিট", "Estimate": "অনুমান",
    "Use for Material": "উপাদানে বসান", "Compare": "তুলনা", "Put in the Design Report": "ডিজাইন রিপোর্টে রাখুন",
}

_lang = "en"


from .i18n_extra import BN_213 as _BN_213  # noqa: E402

for _k, _v in _BN_213.items():
    BN.setdefault(_k, _v)
from .i18n_extra import BN_214 as _BN_214  # noqa: E402
for _k, _v in _BN_214.items():
    BN.setdefault(_k, _v)


def set_language(code: str):
    global _lang
    _lang = code if code in LANGUAGES else "en"


def language() -> str:
    return _lang


def tr(text: str) -> str:
    """Translation of a UI text (with its & accelerator, trailing '...' and shortcut tab kept)."""
    if _lang != "bn" or not text:
        return text
    body, tab = (text.split("\t", 1) + [""])[:2] if "\t" in text else (text, "")
    plain = body.replace("&", "")
    dots = ""
    if plain.endswith("..."):
        plain, dots = plain[:-3], "..."
    elif plain.endswith(":"):
        plain, dots = plain[:-1], ":"
    t = BN.get(plain.strip())
    if t is None:
        return text
    return t + dots + (("\t" + tab) if tab else "")


def translate_widget(w):
    """Translate a widget and its children in place (Qt)."""
    if _lang == "en":
        return
    from PySide6.QtWidgets import (QAbstractButton, QDockWidget, QGroupBox, QLabel, QMenu, QTabWidget,
                                   QWidget)
    widgets = [w] + w.findChildren(QWidget)
    for x in widgets:
        try:
            if x.isWindow() and x.windowTitle():
                x.setWindowTitle(tr(x.windowTitle()))
            if isinstance(x, QMenu):
                x.setTitle(tr(x.title()))
                for a in x.actions():
                    if a.text():
                        a.setText(tr(a.text()))
            elif isinstance(x, (QLabel, QAbstractButton)) and x.text():
                x.setText(tr(x.text()))
            elif isinstance(x, QGroupBox) and x.title():
                x.setTitle(tr(x.title()))
            elif isinstance(x, QTabWidget):
                for i in range(x.count()):
                    x.setTabText(i, tr(x.tabText(i)))
            elif isinstance(x, QDockWidget):
                x.setWindowTitle(tr(x.windowTitle()))
        except RuntimeError:          # deleted while walking
            continue
    if hasattr(w, "menuBar"):
        try:
            for a in w.menuBar().actions():
                a.setText(tr(a.text()))
                if a.menu():
                    translate_widget(a.menu())
        except RuntimeError:
            pass


def install(app):
    """Translate every window as it is shown (dialogs made later included)."""
    from PySide6.QtCore import QEvent, QObject

    class _Filter(QObject):
        def eventFilter(self, obj, ev):
            if ev.type() == QEvent.Show and getattr(obj, "isWindow", lambda: False)():
                translate_widget(obj)
            return False
    f = _Filter(app)
    app.installEventFilter(f)
    return f

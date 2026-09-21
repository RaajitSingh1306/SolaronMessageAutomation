"""
Solaron CRM Template Engine
Provides customizable templates for monthly billing summaries, offline alerts, and yearly milestones.
"""

from typing import Any, Dict

TEMPLATES: Dict[str, Dict[str, str]] = {
    "monthly_standard": {
        "english": (
            "Hello {customer_name}! 🌞\n"
            "Your solar plant *{plant_name}* generated *{generation_kwh:.1f} kWh* "
            "in {month_name}, saving you *₹{savings_inr:.0f}*.\n"
            "CO₂ saved: {co2_saved_kg:.1f} kg 🌱\n"
            "— Solaron Homes"
        ),
        "hindi": (
            "नमस्ते {customer_name}! 🌞\n"
            "आपके सोलर प्लांट *{plant_name}* ने {month_name} में *{generation_kwh:.1f} kWh* "
            "ऊर्जा बनाई, जिससे आपकी *₹{savings_inr:.0f}* की बचत हुई।\n"
            "CO₂ की बचत: {co2_saved_kg:.1f} kg 🌱\n"
            "— सोलरॉन होम्स"
        ),
        "marathi": (
            "नमस्कार {customer_name}! 🌞\n"
            "तुमच्या सोलर प्लांट *{plant_name}* ने {month_name} मध्ये *{generation_kwh:.1f} kWh* "
            "वीज तयार केली, ज्याने तुमची *₹{savings_inr:.0f}* बचत झाली.\n"
            "CO₂ बचत: {co2_saved_kg:.1f} kg 🌱\n"
            "— सोलरॉन होम्स"
        ),
    },
    "offline_alert": {
        "english": (
            "Hello {customer_name},\n"
            "We noticed your solar plant *{plant_name}* has been offline for "
            "{hours_offline:.0f} hours. Our team is aware and a technician will "
            "follow up shortly. Sorry for the inconvenience.\n"
            "— Solaron Homes Support"
        ),
        "hindi": (
            "नमस्ते {customer_name},\n"
            "हमने देखा कि आपका सोलर प्लांट *{plant_name}* पिछले {hours_offline:.0f} घंटों से ऑफलाइन है। "
            "हमारी टीम इसकी जांच कर रही है और जल्द ही आपसे संपर्क करेगी।\n"
            "— सोलरॉन होम्स सपोर्ट"
        ),
    },
    "yearly_milestone": {
        "english": (
            "🎉 Big news, {customer_name}!\n"
            "Your plant *{plant_name}* has now generated *{total_kwh:.0f} kWh* "
            "in {year} — that's enough to power your home for "
            "*{days_powered:.0f} days*!\n"
            "Total savings: *₹{total_savings:.0f}*\n"
            "— Solaron Homes"
        ),
        "hindi": (
            "🎉 बड़ी खुशखबरी, {customer_name}!\n"
            "आपके प्लांट *{plant_name}* ने वर्ष {year} में *{total_kwh:.0f} kWh* ऊर्जा बनाई — "
            "यह आपके घर को *{days_powered:.0f} दिनों* तक चलाने के लिए पर्याप्त है!\n"
            "कुल बचत: *₹{total_savings:.0f}*\n"
            "— सोलरॉन होम्स"
        ),
    },
    "monthly_best": {
        "english": (
            "🌟 Outstanding Performance, {customer_name}!\n"
            "Your solar plant *{plant_name}* generated *{generation_kwh:.1f} kWh* in {month_name}, ranking among our TOP performers! 🏆\n"
            "Savings: *₹{savings_inr:.0f}* | CO₂ avoided: {co2_saved_kg:.1f} kg 🌱\n"
            "Rating: *Best* ⭐⭐⭐\n"
            "📢 *Special Referral Offer*: Love your solar savings? Refer a neighbor and get 1 year of free system maintenance!\n"
            "— Solaron Homes"
        ),
        "hindi": (
            "🌟 शानदार प्रदर्शन, {customer_name}!\n"
            "आपके सोलर प्लांट *{plant_name}* ने {month_name} में *{generation_kwh:.1f} kWh* बिजली पैदा की और हमारे टॉप प्लांट्स में शामिल रहा! 🏆\n"
            "कुल बचत: *₹{savings_inr:.0f}* | CO₂ बचत: {co2_saved_kg:.1f} kg 🌱\n"
            "रेटिंग: *सर्वश्रेष्ठ (Best)* ⭐⭐⭐\n"
            "📢 *विशेष रेफरल ऑफर*: अपने पड़ोसी को सोलरॉन रेफर करें और 1 साल का निःशुल्क मेंटेनेंस पाएं!\n"
            "— सोलरॉन होम्स"
        ),
        "marathi": (
            "🌟 उत्कृष्ट कामगिरी, {customer_name}!\n"
            "तुमच्या सोलर प्लांट *{plant_name}* ने {month_name} मध्ये *{generation_kwh:.1f} kWh* वीज तयार केली आणि टॉप प्लांट्समध्ये स्थान मिळवले! 🏆\n"
            "बचत: *₹{savings_inr:.0f}* | CO₂ बचत: {co2_saved_kg:.1f} kg 🌱\n"
            "रेटिंग: *सर्वोत्कृष्ट (Best)* ⭐⭐⭐\n"
            "📢 *रेफरल ऑफर*: मित्रांना किंवा शेजाऱ्यांना रेफर करा आणि मिळवा 1 वर्ष मोफत मेंटेनन्स!\n"
            "— सोलरॉन होम्स"
        ),
    },
    "monthly_good": {
        "english": (
            "Hello {customer_name}! 🌞\n"
            "Your solar plant *{plant_name}* generated *{generation_kwh:.1f} kWh* in {month_name}, saving you *₹{savings_inr:.0f}*.\n"
            "CO₂ saved: {co2_saved_kg:.1f} kg 🌱\n"
            "Rating: *Good (Steady Performer)* ✅\n"
            "💡 *Tip*: Keep panel surfaces dust-free for an extra 5-10% yield this season!\n"
            "— Solaron Homes"
        ),
        "hindi": (
            "नमस्ते {customer_name}! 🌞\n"
            "आपके सोलर प्लांट *{plant_name}* ने {month_name} में *{generation_kwh:.1f} kWh* ऊर्जा बनाई, जिससे आपकी *₹{savings_inr:.0f}* की बचत हुई।\n"
            "CO₂ बचत: {co2_saved_kg:.1f} kg 🌱\n"
            "रेटिंग: *अच्छा (Good)* ✅\n"
            "💡 *टिप*: सोलर पैनल्स को साफ रखें और 5-10% अधिक बिजली बनाएं!\n"
            "— सोलरॉन होम्स"
        ),
        "marathi": (
            "नमस्कार {customer_name}! 🌞\n"
            "तुमच्या सोलर प्लांट *{plant_name}* ने {month_name} मध्ये *{generation_kwh:.1f} kWh* वीज तयार केली, ज्याने तुमची *₹{savings_inr:.0f}* बचत झाली.\n"
            "CO₂ बचत: {co2_saved_kg:.1f} kg 🌱\n"
            "रेटिंग: *चांगले (Good)* ✅\n"
            "💡 *टीप*: सोलर पॅनेल्स स्वच्छ ठेवा आणि 5-10% जास्त उत्पादन मिळवा!\n"
            "— सोलरॉन होम्स"
        ),
    },
    "monthly_could_better": {
        "english": (
            "Hello {customer_name},\n"
            "Your solar plant *{plant_name}* generated *{generation_kwh:.1f} kWh* in {month_name} (₹{savings_inr:.0f} saved).\n"
            "Rating: *Could Be Better* 📊\n"
            "Our analytics show your plant generated slightly below its optimal benchmark. A quick water rinse or checking for tree shading can restore peak output!\n"
            "Need assistance? Reply to this message for maintenance guidance.\n"
            "— Solaron Homes Support"
        ),
        "hindi": (
            "नमस्ते {customer_name},\n"
            "आपके सोलर प्लांट *{plant_name}* ने {month_name} में *{generation_kwh:.1f} kWh* ऊर्जा बनाई (₹{savings_inr:.0f} बचत)।\n"
            "रेटिंग: *और बेहतर हो सकता है (Could Be Better)* 📊\n"
            "हमारा डेटा दिखाता है कि उत्पादन क्षमता से थोड़ा कम रहा। पैनल्स को पानी से धोने या छाया की जांच करने से उत्पादन बढ़ सकता है।\n"
            "सहायता के लिए इस संदेश का उत्तर दें।\n"
            "— सोलरॉन होम्स सपोर्ट"
        ),
        "marathi": (
            "नमस्कार {customer_name},\n"
            "तुमच्या सोलर प्लांट *{plant_name}* ने {month_name} मध्ये *{generation_kwh:.1f} kWh* वीज तयार केली (₹{savings_inr:.0f} बचत).\n"
            "रेटिंग: *अजून चांगले होऊ शकते (Could Be Better)* 📊\n"
            "उत्पादन क्षमतेपेक्षा थोडे कमी राहिले आहे. पॅनेल्सची स्वच्छता केल्यास उत्पादन वाढू शकते.\n"
            "मदतीसाठी या मेसेजला रिप्लाय करा.\n"
            "— सोलरॉन होम्स सपोर्ट"
        ),
    },
    "monthly_needs_attention": {
        "english": (
            "⚠️ Service Advisory for {customer_name}\n"
            "Your solar plant *{plant_name}* generated *{generation_kwh:.1f} kWh* in {month_name}, which is significantly below expected output.\n"
            "Rating: *Needs Attention / Critical* 🚨\n"
            "Potential cause: Inverter fault, grid disconnection, or heavy soiling.\n"
            "📞 *Action Required*: Our technical team is ready to inspect your system. Please reply or call support immediately to restore generation!\n"
            "— Solaron Homes Service Team"
        ),
        "hindi": (
            "⚠️ महत्वपूर्ण सूचना: {customer_name}\n"
            "आपके सोलर प्लांट *{plant_name}* ने {month_name} में *{generation_kwh:.1f} kWh* ऊर्जा बनाई, जो अनुमानित उत्पादन से काफी कम है।\n"
            "रेटिंग: *ध्यान देने योग्य / क्रिटिकल (Needs Attention)* 🚨\n"
            "संभावित कारण: इन्वर्टर फॉल्ट, ग्रिड डिस्कनेक्शन या अत्यधिक धूल।\n"
            "📞 *कार्रवाई आवश्यक*: हमारी टेक्निकल टीम जांच के लिए उपलब्ध है। कृपया तुरंत संपर्क करें!\n"
            "— सोलरॉन होम्स सर्विस टीम"
        ),
        "marathi": (
            "⚠️ सेवा सूचना: {customer_name}\n"
            "तुमच्या सोलर प्लांट *{plant_name}* ने {month_name} मध्ये *{generation_kwh:.1f} kWh* वीज तयार केली, जे अपेक्षेपेक्षा खूपच कमी आहे।\n"
            "रेटिंग: *लक्ष देणे आवश्यक (Needs Attention)* 🚨\n"
            "संभाव्य कारण: इन्व्हर्टर फॉल्ट किंवा जास्त धूळ.\n"
            "📞 *तातडीने संपर्क साधा*: आमची तांत्रिक टीम मदतीसाठी सज्ज आहे. कृपया लगेच कॉल करा!\n"
            "— सोलरॉन होम्स सर्व्हिस टीम"
        ),
    }
}


def render(template_key: str, data: Any, lang: str = "english", **kwargs) -> str:
    """
    Renders a message template using attributes from data or dictionary keys.
    Falls back to 'english' if lang is not found.
    """
    category = TEMPLATES.get(template_key)
    if not category:
        raise KeyError(f"Template key '{template_key}' not found.")

    template_str = category.get(lang.lower()) or category.get("english")
    if not template_str:
        template_str = list(category.values())[0]

    # Build context dictionary
    context: Dict[str, Any] = {}
    if isinstance(data, dict):
        context.update(data)
    elif hasattr(data, "__dict__"):
        context.update(data.__dict__)

    context.update(kwargs)

    # Defaults for safe interpolation
    context.setdefault("customer_name", "Valued Customer")
    context.setdefault("plant_name", "Solar Plant")
    context.setdefault("generation_kwh", 0.0)
    context.setdefault("savings_inr", 0.0)
    context.setdefault("co2_saved_kg", 0.0)
    context.setdefault("month_name", "the previous month")
    context.setdefault("hours_offline", 24.0)
    context.setdefault("total_kwh", 0.0)
    context.setdefault("total_savings", 0.0)
    context.setdefault("days_powered", 0.0)
    context.setdefault("year", "2025")
    context.setdefault("performance_rating", "Good")
    context.setdefault("marketing_cta", "")

    try:
        return template_str.format(**context)
    except Exception as e:
        # Fallback safe format if missing key
        return f"Hello {context.get('customer_name')}, your plant {context.get('plant_name')} generated {context.get('generation_kwh', 0):.1f} kWh."

# تشغيل Deeptech DZ على جهازك

1. **المستودع:** أنشئ مستودعاً خاصاً فارغاً على GitHub باسم `deeptech-dz` (دون README).
2. **القناة:** أنشئ قناة عامة في تيليجرام واختر اسم المستخدم (مثل `@DeeptechDZ`).
3. **البوت:** من @BotFather أرسل `/newbot`، واحفظ التوكن، ثم أضف البوت **مشرفاً** في القناة بصلاحية النشر.
4. فك الضغط إلى مجلد ثابت، مثل `C:\deeptech-dz`.
5. شغّل `start-bot.bat`. سيفتح `settings.txt`: ضع `BOT_TOKEN` و`CHANNEL`، احفظ، ثم شغّل `start-bot.bat` مرة ثانية.
6. أرسل `/id` للبوت في الخاص، ضع الرقم في `ADMIN_ID`، ثم شغّل `update-bot.bat`.
7. سيرسل لك البوت **مفتاحاً عاماً** (يبدأ بـ `ssh-ed25519`). أضفه في المستودع:
   Settings ← Deploy keys ← Add deploy key ← فعّل **Allow write access**.
   أو أرسله إلى Claude ليضيفه.
8. خلال دقائق تصلك رسالة «✅ الربط مع GitHub يعمل». أرسل `/status` للتأكد.

أوامر البوت: `/status` `/queue` `/health` `/pause` `/resume`
السجل: `logs.bat`

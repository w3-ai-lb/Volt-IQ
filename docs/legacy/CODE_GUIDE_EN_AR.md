# Code walkthrough / شرح الكود

## 1. The overall flow / المسار الكامل

`START_APP.bat → python.cmd → launcher.py → builds + database + servers → portal/index.html`

English: The portal is a navigation shell around the two real applications. It does not replace their screens, merge their accounts, or copy CRM records into analytics. Each application keeps its own code and data flow.

العربية: البوابة واجهة انتقال بين التطبيقين الحقيقيين. لا تستبدل شاشاتهما ولا توحّد حساباتهما أو تنقل سجلات CRM إلى التحليلات. لكل تطبيق كوده ومسار بياناته المستقل.

## 2. Startup files / ملفات التشغيل

`START_APP.bat` moves into its own folder and calls `python.cmd launcher.py start`. `python.cmd` locates a compatible Python installation, including the existing bundled runtime on this computer. `STOP_APP.bat` calls the same launcher with `stop`.

ينتقل ملف التشغيل إلى مجلده قبل تنفيذ الأوامر، لذلك يعمل حتى لو فتحته من مكان آخر. ملف الإيقاف يطلب من المشغّل إنهاء الخدمات التي يديرها فقط. يجب إبقاء نافذة التشغيل مفتوحة أثناء الاستخدام.

## 3. Configuration / الإعدادات

`config.json` holds relative source paths and four local ports. `paths()` resolves the paths and checks important entry files. `node_binary()` checks the Node version before any frontend work.

يحدّد ملف الإعدادات مكان المشروعين ومنافذ الخدمات. المسارات نسبية لتسهيل نقل المجلدات معًا. إذا نقلت مشروعًا وحده، عدّل مساره في هذا الملف. فحص الملفات الأساسية يكشف المسار الخاطئ برسالة واضحة.

## 4. Preparation / التحضير

`prepare()` creates a Python virtual environment, installs the backend requirements, snapshots the application source into `.runtime`, installs frontend packages using their lockfiles, and builds the frontends. Hash markers let later starts skip unchanged completed stages.

الدالة `prepare()` تثبّت المكتبات داخل بيئة منفصلة، وتنسخ ملفات العمل إلى `.runtime`، ثم تبني واجهتي المستخدم. بصمات الملفات تكشف التغييرات وتمنع إعادة المراحل المكتملة عند كل تشغيل. النسخ الأصلية لا تتغير.

`snapshot()` excludes generated dependencies, build output and database files. The frontend build receives the managed analytics API address. CRM keeps the original Supabase configuration.

الدالة `snapshot()` لا تنسخ المكتبات المثبّتة أو قواعد البيانات ضمن نسخ الكود. عنوان API الخاص بالتحليلات يُضبط على الخدمة المحلية، بينما يحتفظ CRM بإعداد Supabase الخاص به.

## 5. Database / قاعدة البيانات

The launcher uses `.runtime/energy_analytics.db`. If the original default SQLite database exists, SQLite's backup API makes a separate copy. Otherwise the original seeder creates synthetic demo data. Later starts preserve this file. A random JWT signing secret is generated once and retained locally.

قاعدة التحليلات المحلية مستقلة. عند وجود قاعدة أصلية افتراضية تُنسخ بأداة النسخ الاحتياطي الخاصة بـ SQLite؛ وإلا تُنشأ بيانات تجريبية بواسطة كود المشروع الأصلي. إعادة التشغيل لا تمسح البيانات. مفتاح توقيع الجلسات يُنشأ مرة واحدة ويُحفظ محليًا.

The CRM does not use this SQLite database. Its browser code calls Supabase directly. A downloaded GitHub repository supplies code, but does not necessarily supply an active hosted database, its data or access permissions.

CRM لا يستخدم قاعدة SQLite هذه؛ المتصفح يتصل مباشرةً بـ Supabase. تنزيل المشروع من GitHub يوفّر الكود، لكنه لا يضمن وجود قاعدة سحابية فعّالة أو بياناتها وصلاحيات الوصول إليها.

## 6. Servers and lifecycle / الخدمات ودورة التشغيل

The launcher starts FastAPI as a child process and waits for its health endpoint. Standard-library HTTP servers deliver the portal and the two built frontends. They listen only on `127.0.0.1`. Missing extensionless frontend routes fall back to `index.html`, so React Router can handle refreshes.

يبدأ المشغّل خدمة FastAPI ويتحقق من جاهزيتها، ثم يقدّم البوابة وملفات الواجهتين. الاستماع محلي على الجهاز فقط. عند تحديث صفحة داخلية، يعيد خادم الواجهة ملف `index.html` ليكمل React تحديد الصفحة المطلوبة.

An exclusive lock prevents duplicate launchers. Port checks report conflicts without terminating their owners. A Windows Job Object ties managed child processes to the launcher. Normal shutdown closes the HTTP servers and stops the API. The stop endpoint requires a locally generated control token.

قفل التشغيل يمنع تشغيل نسختين متعارضتين. إذا كان منفذ مستخدمًا، تظهر رسالة دون إغلاق البرنامج الآخر. في Windows ترتبط العمليات التابعة بالمشغّل حتى تُغلق معه. طلب الإيقاف يحتاج رمز تحكم محليًا.

## 7. Portal / البوابة

`portal/index.html` contains the layout, responsive CSS and a small script. `refresh()` requests `/status` for configured application URLs and local API health. `select()` creates an iframe on first use, keeps it alive, and switches visibility. The URL hash remembers the selected application across a portal refresh.

ملف البوابة يتضمن التصميم وقواعد العرض على الشاشات الصغيرة وكود الانتقال. الدالة `refresh()` تقرأ حالة الخدمات وعناوينها. الدالة `select()` تفتح التطبيق داخل إطار وتحافظ عليه أثناء الانتقال بين التطبيقين. الجزء بعد `#` في الرابط يحفظ اختيار التطبيق عند تحديث البوابة، لكنه لا يحفظ كل الحالات الداخلية للتطبيق.

## 8. Analytics code / كود التحليلات

Frontend `src/main.tsx` mounts the React application. `App.tsx` selects pages using routes. `src/services/api.ts` centralizes API calls and attaches session authorization. A user action reaches a FastAPI route; dependency checks identify the user and permissions; SQLAlchemy reads or writes the local database; JSON returns to React for rendering.

يبدأ عرض React من `src/main.tsx`، وتحدّد المسارات في `App.tsx` الصفحة المطلوبة. ملف `src/services/api.ts` ينظم الاتصال بالخادم ويرفق بيانات الجلسة. يستقبل FastAPI الطلب، يتحقق من المستخدم والصلاحيات، ثم يتعامل SQLAlchemy مع قاعدة البيانات وتعود النتيجة إلى الواجهة بصيغة JSON.

Backend `app/main.py` assembles the API, `app/config.py` reads settings, and `app/database.py` creates the engine and sessions. Models describe database entities; routes implement actions; pipeline modules prepare analytical data. Changing the portal does not change these business rules.

ملف `app/main.py` يركّب خدمة API، و`app/config.py` يقرأ الإعدادات، و`app/database.py` يجهّز الاتصال والجلسات. النماذج تصف السجلات، ومسارات API تنفّذ العمليات، ووحدات التحليل تعالج البيانات. البوابة لا تغيّر قواعد العمل هذه.

## 9. CRM code / كود إدارة المشتركين

`src/main.jsx` mounts `App.jsx`. The app changes sections using React state. `AuthContext` holds the existing demo sign-in state; `DataContext` loads and manages business records; `src/lib/supabaseClient.js` creates the Supabase client. Remote changes depend on table schemas, access policies and a reachable Supabase project.

يبدأ CRM من `src/main.jsx` ثم `App.jsx`. الانتقال بين الأقسام يعتمد على حالة React وليس مسارات مستقلة. `AuthContext` يحتفظ بحالة الدخول التجريبية الحالية، و`DataContext` يدير السجلات، و`src/lib/supabaseClient.js` يجهّز الاتصال بـ Supabase. نجاح الحفظ والمزامنة يحتاج قاعدة فعّالة وجداول وصلاحيات صحيحة.

The existing CRM sign-in implementation is permissive and demo-oriented. Rendering its dashboard is not proof of secure authentication or successful remote synchronization. Its SQL setup file contains destructive statements and is never run by this launcher.

تسجيل الدخول الحالي في CRM تجريبي ومتساهل. ظهور لوحة التحكم لا يثبت أمان الحسابات أو نجاح المزامنة. ملف إعداد SQL يحتوي تعليمات حذف؛ المشغّل لا ينفّذه.

## 10. Verification and future hosting / التحقق والاستضافة لاحقًا

`verify.py` checks actual HTTP responses, built assets, API authorization, representative analytics workflows, duplicate startup, shutdown, restart and port ownership. `check_crm.py` checks required remote tables without changing records or printing credentials. See `INTEGRATION_REPORT.md` for observed results and remaining blockers.

ملف `verify.py` يختبر الخدمات والملفات والصلاحيات وبعض عمليات التحليلات، إضافةً إلى الإيقاف وإعادة التشغيل وتعارض المنافذ. ملف `check_crm.py` يفحص الاتصال بالجداول الخارجية دون تعديل البيانات أو طباعة المفاتيح. نتائج التنفيذ الفعلية في تقرير التكامل.

This launcher is a local integration, not a cloud deployment or an offline conversion of CRM. Future local/cloud/hybrid sales require explicit work on CRM backend portability, production authentication, mobile endpoints and OCR/LLM provider configuration. The current integration keeps those boundaries visible rather than implying that a local frontend makes Supabase-dependent operations offline.

هذا تشغيل محلي موحّد، وليس نشرًا سحابيًا أو تحويلًا لـ CRM ليعمل دون الإنترنت. سيناريوهات البيع المحلية والسحابية والهجينة تحتاج عملًا إضافيًا على قابلية نقل خادم CRM وأمان الحسابات وعناوين تطبيق الهاتف وإعداد مزوّدي OCR وLLM. تشغيل الواجهة محليًا وحده لا يجعل العمليات المعتمدة على Supabase محلية.

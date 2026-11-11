"""
Every sentence the backend writes for a page, in the seven interface languages.

See app/core/i18n.py for how these are used. Each entry is the English exactly
as the code writes it, with its variable parts marked:

    {name}            carried over as written
    {name:num}        a number, carried over as written
    {name:money}      an amount with its currency, carried over as written
    {name:date}       '31 Mar 2025', written as a date in the reader's language
    {name:monthyear}  'Jun 2026' or 'June 2026', likewise
    {name:monthname}  'June', likewise
    {name:sub}        another sentence from this catalogue, translated in turn
    {name:expr}       the inside of a bracket, such as 'cv=2.32', carried over

The translations use the same names without the kind. An entry whose English
changes in the code stops matching, and the tests say so.

Arabic is Modern Standard Arabic, with the Levantine month names. Where a noun
follows a number, Arabic has five forms, written out with `Plural`.

Grouped by the module that writes the English.
"""

from app.core.i18n import Message as M, Plural

MESSAGES: list[M] = [
    # ------------------------------------------------------------------
    # app/ai/recommender.py: titles and descriptions
    # ------------------------------------------------------------------
    M("Shift laundry and dishwashing to off-peak hours",
      ar="انقل الغسيل وجلي الصحون إلى خارج ساعات الذروة",
      es="Pasa la colada y el lavavajillas fuera de las horas punta",
      fr="Décalez la lessive et la vaisselle en dehors des heures de pointe",
      de="Wäsche und Geschirrspülen außerhalb der Spitzenzeit erledigen",
      zh="把洗衣和洗碗安排在用电高峰之外",
      ja="洗濯と食器洗いをピーク時間帯以外に移す"),
    M("{pct:num}% of your electricity is used during the 6pm-10pm peak window. Running your washer, "
      "dryer and dishwasher between 10pm and 6am can cut your monthly bill by up to 12%.",
      ar="{pct}% من الكهرباء التي تستهلكها تُستخدم في فترة الذروة بين 6 مساءً و10 ليلاً. تشغيل الغسالة "
         "والنشافة وجلّاية الصحون بين 10 ليلاً و6 صباحاً قد يخفّض فاتورتك الشهرية حتى 12%.",
      es="El {pct}% de tu electricidad se consume en la franja punta de 18:00 a 22:00. Usar la lavadora, "
         "la secadora y el lavavajillas entre las 22:00 y las 6:00 puede reducir tu factura mensual hasta un 12%.",
      fr="{pct} % de votre électricité est consommée pendant la pointe de 18 h à 22 h. Faire tourner "
         "lave-linge, sèche-linge et lave-vaisselle entre 22 h et 6 h peut réduire votre facture mensuelle "
         "jusqu’à 12 %.",
      de="{pct} % Ihres Stroms verbrauchen Sie in der Spitzenzeit von 18 bis 22 Uhr. Wenn Waschmaschine, "
         "Trockner und Geschirrspüler zwischen 22 und 6 Uhr laufen, kann Ihre Monatsrechnung um bis zu 12 % sinken.",
      zh="您有 {pct}% 的用电发生在晚上 6 点至 10 点的高峰时段。把洗衣机、烘干机和洗碗机安排在晚上 10 点至"
         "早上 6 点运行，每月电费最多可降低 12%。",
      ja="電力の{pct}%を午後6時から10時のピーク時間帯に使っています。洗濯機・乾燥機・食器洗い機を午後10時から"
         "午前6時の間に使うと、月々の請求額を最大12%減らせます。"),
    M("Unplug idle electronics and chargers",
      ar="افصل الأجهزة الإلكترونية والشواحن غير المستخدمة",
      es="Desenchufa los aparatos y cargadores que no uses",
      fr="Débranchez les appareils et chargeurs inutilisés",
      de="Ungenutzte Geräte und Ladegeräte ausstecken",
      zh="拔掉闲置的电子设备和充电器",
      ja="使っていない電子機器や充電器のプラグを抜く"),
    M("Your overnight baseload stays unusually high relative to daytime usage, which points to standby "
      "draw. Phantom loads account for roughly 8% of residential electricity use.",
      ar="يبقى استهلاكك الأساسي ليلاً مرتفعاً على نحو غير معتاد مقارنةً بالاستهلاك نهاراً، ما يشير إلى أجهزة "
         "في وضع الاستعداد. ويمثّل هذا الاستهلاك الخفي نحو 8% من استهلاك الكهرباء في المنازل.",
      es="Tu consumo base nocturno se mantiene inusualmente alto respecto al diurno, lo que apunta a aparatos "
         "en espera. Estos consumos fantasma suponen alrededor del 8% del consumo eléctrico doméstico.",
      fr="Votre consommation de fond la nuit reste anormalement élevée par rapport à la journée, ce qui indique "
         "des appareils en veille. Ces consommations fantômes représentent environ 8 % de l’électricité des ménages.",
      de="Ihre nächtliche Grundlast bleibt im Verhältnis zum Tagesverbrauch ungewöhnlich hoch, was auf "
         "Standby-Verbrauch hindeutet. Solche versteckten Verbräuche machen rund 8 % des Haushaltsstroms aus.",
      zh="您夜间的基础用电相对白天偏高，说明有设备处于待机耗电状态。待机耗电约占家庭用电的 8%。",
      ja="夜間のベースロードが昼間の使用量に比べて異常に高く、待機電力が原因と考えられます。待機電力は家庭の"
         "電力使用量の約8%を占めます。"),
    M("Upgrade to a smart thermostat",
      ar="استخدم ثرموستاتاً ذكياً",
      es="Instala un termostato inteligente",
      fr="Passez à un thermostat intelligent",
      de="Auf ein smartes Thermostat umsteigen",
      zh="升级为智能温控器",
      ja="スマートサーモスタットに切り替える"),
    M("Your summer consumption runs well above your winter baseline, so cooling dominates your bill. "
      "A programmable thermostat optimises HVAC cycles and typically reduces cooling costs by 10-15%.",
      ar="استهلاكك في الصيف أعلى بكثير من مستواه في الشتاء، لذا يشكّل التبريد الجزء الأكبر من فاتورتك. "
         "يضبط الثرموستات القابل للبرمجة دورات التكييف ويخفّض عادةً كلفة التبريد بنسبة 10-15%.",
      es="Tu consumo en verano supera con creces tu nivel de invierno, así que la refrigeración domina tu "
         "factura. Un termostato programable optimiza los ciclos de climatización y suele reducir el coste de "
         "refrigeración entre un 10 y un 15%.",
      fr="Votre consommation estivale dépasse nettement votre niveau d’hiver : la climatisation pèse le plus "
         "sur votre facture. Un thermostat programmable optimise les cycles de climatisation et réduit en "
         "général les coûts de refroidissement de 10 à 15 %.",
      de="Ihr Sommerverbrauch liegt deutlich über Ihrem Winterniveau, die Kühlung bestimmt also Ihre "
         "Rechnung. Ein programmierbares Thermostat optimiert die Klimatisierungszyklen und senkt die "
         "Kühlkosten meist um 10–15 %.",
      zh="您夏季的用电量远高于冬季基线，制冷是电费的主要部分。可编程温控器能优化空调运行周期，"
         "通常可将制冷费用降低 10-15%。",
      ja="夏の消費量が冬の基準を大きく上回っており、冷房が請求額の大半を占めています。プログラム式サーモ"
         "スタットは空調の運転サイクルを最適化し、冷房費を通常10〜15%削減します。"),
    M("Schedule air-conditioning maintenance",
      ar="حدّد موعداً لصيانة المكيّف",
      es="Programa el mantenimiento del aire acondicionado",
      fr="Planifiez l’entretien de la climatisation",
      de="Wartung der Klimaanlage einplanen",
      zh="安排空调保养",
      ja="エアコンの点検を予約する"),
    M("A clean filter and tuned coils improve cooling efficiency by 5-15%. Given your cooling-heavy "
      "profile this pays back within one season.",
      ar="الفلتر النظيف والملفات المضبوطة يحسّنان كفاءة التبريد بنسبة 5-15%. ومع اعتماد استهلاكك الكبير على "
         "التبريد، تُسترد الكلفة خلال موسم واحد.",
      es="Un filtro limpio y unas baterías a punto mejoran la eficiencia de refrigeración entre un 5 y un 15%. "
         "Con tu perfil de alto uso de refrigeración, se amortiza en una temporada.",
      fr="Un filtre propre et des batteries bien réglées améliorent le rendement du refroidissement de 5 à "
         "15 %. Avec votre profil très axé sur la climatisation, c’est rentabilisé en une saison.",
      de="Ein sauberer Filter und eingestellte Wärmetauscher verbessern die Kühleffizienz um 5–15 %. Bei "
         "Ihrem kühlungsintensiven Verbrauch amortisiert sich das innerhalb einer Saison.",
      zh="清洁的滤网和调校好的盘管可将制冷效率提高 5-15%。以您以制冷为主的用电情况，一个季节内即可收回成本。",
      ja="フィルターを清掃しコイルを調整すると、冷房効率が5〜15%向上します。冷房中心の使い方なら、"
         "1シーズンで元が取れます。"),
    M("Replace remaining incandescent bulbs with LEDs",
      ar="استبدل ما تبقّى من المصابيح المتوهّجة بمصابيح LED",
      es="Cambia las bombillas incandescentes que quedan por LED",
      fr="Remplacez les ampoules à incandescence restantes par des LED",
      de="Verbleibende Glühbirnen durch LEDs ersetzen",
      zh="将剩余的白炽灯换成 LED 灯",
      ja="残っている白熱電球をLEDに交換する"),
    M("At {kwh:num} kWh/month your household is in the upper consumption band. LEDs use up to 80% less "
      "energy than incandescent lighting and last around 25 times longer.",
      ar="باستهلاك {kwh} kWh شهرياً، يقع منزلك ضمن الشريحة العليا للاستهلاك. تستهلك مصابيح LED طاقة أقل بنسبة "
         "تصل إلى 80% من المصابيح المتوهّجة وتدوم نحو 25 مرة أطول.",
      es="Con {kwh} kWh al mes, tu hogar está en la franja alta de consumo. Las LED consumen hasta un 80% "
         "menos que las incandescentes y duran unas 25 veces más.",
      fr="Avec {kwh} kWh par mois, votre foyer se situe dans la tranche de consommation haute. Les LED "
         "consomment jusqu’à 80 % d’énergie en moins que l’incandescence et durent environ 25 fois plus longtemps.",
      de="Mit {kwh} kWh im Monat gehört Ihr Haushalt zum oberen Verbrauchsbereich. LEDs brauchen bis zu 80 % "
         "weniger Energie als Glühlampen und halten etwa 25-mal länger.",
      zh="您家每月用电 {kwh} kWh，属于高用电档。LED 灯比白炽灯最多节能 80%，寿命约长 25 倍。",
      ja="月{kwh} kWhのご家庭は消費量の多い層に入ります。LEDは白熱電球より最大80%少ない電力で済み、"
         "寿命は約25倍です。"),
    M("Enable monthly usage alerts",
      ar="فعّل تنبيهات الاستهلاك الشهرية",
      es="Activa las alertas mensuales de consumo",
      fr="Activez les alertes mensuelles de consommation",
      de="Monatliche Verbrauchswarnungen aktivieren",
      zh="开启每月用电提醒",
      ja="毎月の使用量アラートを有効にする"),
    M("Your consumption is already well controlled. Turning on usage alerts will notify you early if your "
      "pattern changes unexpectedly.",
      ar="استهلاكك منضبط أصلاً. سيُعلمك تفعيل تنبيهات الاستهلاك مبكراً إذا تغيّر نمط استهلاكك على نحو غير متوقّع.",
      es="Tu consumo ya está bien controlado. Activar las alertas de consumo te avisará pronto si tu patrón "
         "cambia de forma inesperada.",
      fr="Votre consommation est déjà bien maîtrisée. Les alertes de consommation vous préviendront tôt si vos "
         "habitudes changent de façon inattendue.",
      de="Ihr Verbrauch ist bereits gut im Griff. Mit Verbrauchswarnungen erfahren Sie früh, wenn sich Ihr "
         "Muster unerwartet ändert.",
      zh="您的用电已经控制得很好。开启用电提醒后，一旦用电模式意外变化，您会第一时间收到通知。",
      ja="消費量はすでによく管理されています。使用量アラートを有効にすると、パターンが予期せず変わったときに"
         "早めにお知らせします。"),

    # ------------------------------------------------------------------
    # app/ai/alerts.py: titles
    # ------------------------------------------------------------------
    M("Your consumption is above your usual level",
      ar="استهلاكك أعلى من مستواه المعتاد",
      es="Tu consumo está por encima de lo habitual",
      fr="Votre consommation dépasse son niveau habituel",
      de="Ihr Verbrauch liegt über dem üblichen Niveau",
      zh="您的用电高于平常水平",
      ja="消費量がいつもより多くなっています"),
    M("Your consumption is down",
      ar="انخفض استهلاكك",
      es="Tu consumo ha bajado",
      fr="Votre consommation a baissé",
      de="Ihr Verbrauch ist gesunken",
      zh="您的用电量下降了",
      ja="消費量が減りました"),
    M("You have an overdue bill",
      ar="لديك فاتورة متأخرة",
      es="Tienes una factura vencida",
      fr="Vous avez une facture en retard",
      de="Sie haben eine überfällige Rechnung",
      zh="您有逾期账单",
      ja="支払期限を過ぎた請求書があります"),
    M("Payment due soon",
      ar="موعد الدفع قريب",
      es="Pago próximo a vencer",
      fr="Paiement bientôt dû",
      de="Zahlung bald fällig",
      zh="即将到期付款",
      ja="まもなく支払期限です"),
    M("Your bill is ready",
      ar="فاتورتك جاهزة",
      es="Tu factura está lista",
      fr="Votre facture est prête",
      de="Ihre Rechnung ist da",
      zh="您的账单已出",
      ja="請求書が発行されました"),
    M("Unusual reading detected: {kind:sub}",
      ar="رُصدت قراءة غير اعتيادية: {kind}",
      es="Lectura inusual detectada: {kind}",
      fr="Relevé inhabituel détecté : {kind}",
      de="Ungewöhnlicher Zählerstand erkannt: {kind}",
      zh="检测到异常读数：{kind}",
      ja="異常な検針値を検出しました：{kind}"),

    # ------------------------------------------------------------------
    # app/ai/alerts.py: usage messages
    # ------------------------------------------------------------------
    M("You used {recent:num} kWh in the last 30 days. That is {pct:num}% more than your typical level for "
      "the same length of time, which was {base:num} kWh. Check for an appliance left running, or cooling "
      "that is working harder than usual.",
      ar="استهلكت {recent} kWh في آخر 30 يوماً، أي أكثر بنسبة {pct}% من مستواك المعتاد للمدة نفسها، الذي كان "
         "{base} kWh. تحقّق من وجود جهاز تُرك يعمل، أو من تبريد يعمل أكثر من المعتاد.",
      es="Consumiste {recent} kWh en los últimos 30 días, un {pct}% más que tu nivel habitual para el mismo "
         "periodo, que era de {base} kWh. Comprueba si hay algún aparato encendido o una refrigeración "
         "trabajando más de lo normal.",
      fr="Vous avez consommé {recent} kWh au cours des 30 derniers jours, soit {pct} % de plus que votre "
         "niveau habituel sur la même durée, qui était de {base} kWh. Vérifiez qu’aucun appareil n’est resté "
         "allumé et que la climatisation ne force pas plus que d’habitude.",
      de="Sie haben in den letzten 30 Tagen {recent} kWh verbraucht, {pct} % mehr als Ihr übliches Niveau "
         "für denselben Zeitraum, das bei {base} kWh lag. Prüfen Sie, ob ein Gerät eingeschaltet geblieben "
         "ist oder die Kühlung stärker arbeitet als sonst.",
      zh="您在过去 30 天用电 {recent} kWh，比同期的平常水平 {base} kWh 高 {pct}%。请检查是否有电器忘关，"
         "或空调运行得比平时更吃力。",
      ja="直近30日間の使用量は{recent} kWhで、同じ期間のいつもの水準{base} kWhより{pct}%多くなっています。"
         "電源を切り忘れた機器がないか、冷房がいつもより強く働いていないか確認してください。"),
    M("You used {recent:num} kWh in the month to {date:date}. That is {pct:num}% more than you used in "
      "{month:monthname} last year, when it was {base:num} kWh. Check for an appliance left running, or "
      "cooling that is working harder than usual.",
      ar="استهلكت {recent} kWh في الشهر المنتهي في {date}، أي أكثر بنسبة {pct}% مما استهلكته في {month} من "
         "العام الماضي، حين كان {base} kWh. تحقّق من وجود جهاز تُرك يعمل، أو من تبريد يعمل أكثر من المعتاد.",
      es="Consumiste {recent} kWh en el mes hasta el {date}, un {pct}% más que en {month} del año pasado, "
         "cuando fueron {base} kWh. Comprueba si hay algún aparato encendido o una refrigeración trabajando "
         "más de lo normal.",
      fr="Vous avez consommé {recent} kWh sur le mois se terminant le {date}, soit {pct} % de plus qu’en "
         "{month} l’an dernier, où c’était {base} kWh. Vérifiez qu’aucun appareil n’est resté allumé et que "
         "la climatisation ne force pas plus que d’habitude.",
      de="Sie haben im Monat bis zum {date} {recent} kWh verbraucht, {pct} % mehr als im {month} des "
         "Vorjahres, als es {base} kWh waren. Prüfen Sie, ob ein Gerät eingeschaltet geblieben ist oder die "
         "Kühlung stärker arbeitet als sonst.",
      zh="截至 {date} 的一个月内，您用电 {recent} kWh，比去年 {month} 的 {base} kWh 高 {pct}%。"
         "请检查是否有电器忘关，或空调运行得比平时更吃力。",
      ja="{date}までの1か月の使用量は{recent} kWhで、昨年{month}の{base} kWhより{pct}%多くなっています。"
         "電源を切り忘れた機器がないか、冷房がいつもより強く働いていないか確認してください。"),
    M("You used {recent:num} kWh in the month to {date:date}. That is {pct:num}% more than the average of "
      "your recent months, which was {base:num} kWh. Until you have a year of history, that is the best "
      "comparison available. Check for an appliance left running, or cooling that is working harder than usual.",
      ar="استهلكت {recent} kWh في الشهر المنتهي في {date}، أي أكثر بنسبة {pct}% من متوسط أشهرك الأخيرة، الذي "
         "كان {base} kWh. وإلى أن يتوفّر لديك سجلّ لعام كامل، فهذه أفضل مقارنة متاحة. تحقّق من وجود جهاز تُرك "
         "يعمل، أو من تبريد يعمل أكثر من المعتاد.",
      es="Consumiste {recent} kWh en el mes hasta el {date}, un {pct}% más que la media de tus últimos meses, "
         "que era de {base} kWh. Hasta que tengas un año de historial, es la mejor comparación posible. "
         "Comprueba si hay algún aparato encendido o una refrigeración trabajando más de lo normal.",
      fr="Vous avez consommé {recent} kWh sur le mois se terminant le {date}, soit {pct} % de plus que la "
         "moyenne de vos derniers mois, qui était de {base} kWh. Tant que vous n’avez pas un an d’historique, "
         "c’est la meilleure comparaison possible. Vérifiez qu’aucun appareil n’est resté allumé et que la "
         "climatisation ne force pas plus que d’habitude.",
      de="Sie haben im Monat bis zum {date} {recent} kWh verbraucht, {pct} % mehr als der Durchschnitt Ihrer "
         "letzten Monate, der bei {base} kWh lag. Solange Sie keine Jahreshistorie haben, ist das der beste "
         "verfügbare Vergleich. Prüfen Sie, ob ein Gerät eingeschaltet geblieben ist oder die Kühlung stärker "
         "arbeitet als sonst.",
      zh="截至 {date} 的一个月内，您用电 {recent} kWh，比您最近几个月的平均值 {base} kWh 高 {pct}%。"
         "在您有满一年的记录之前，这是能做的最佳比较。请检查是否有电器忘关，或空调运行得比平时更吃力。",
      ja="{date}までの1か月の使用量は{recent} kWhで、直近数か月の平均{base} kWhより{pct}%多くなっています。"
         "1年分の履歴がそろうまでは、これが最も適切な比較です。電源を切り忘れた機器がないか、冷房がいつもより"
         "強く働いていないか確認してください。"),
    M("You used {recent:num} kWh in the last 30 days. That is {pct:num}% less than your typical level for "
      "the same length of time, which was {base:num} kWh. Whatever you changed is working.",
      ar="استهلكت {recent} kWh في آخر 30 يوماً، أي أقل بنسبة {pct}% من مستواك المعتاد للمدة نفسها، الذي كان "
         "{base} kWh. ما غيّرته يؤتي ثماره.",
      es="Consumiste {recent} kWh en los últimos 30 días, un {pct}% menos que tu nivel habitual para el mismo "
         "periodo, que era de {base} kWh. Lo que hayas cambiado está funcionando.",
      fr="Vous avez consommé {recent} kWh au cours des 30 derniers jours, soit {pct} % de moins que votre "
         "niveau habituel sur la même durée, qui était de {base} kWh. Ce que vous avez changé porte ses fruits.",
      de="Sie haben in den letzten 30 Tagen {recent} kWh verbraucht, {pct} % weniger als Ihr übliches Niveau "
         "für denselben Zeitraum, das bei {base} kWh lag. Was Sie geändert haben, wirkt.",
      zh="您在过去 30 天用电 {recent} kWh，比同期的平常水平 {base} kWh 低 {pct}%。您做出的改变见效了。",
      ja="直近30日間の使用量は{recent} kWhで、同じ期間のいつもの水準{base} kWhより{pct}%少なくなっています。"
         "変えたことが効果を上げています。"),
    M("You used {recent:num} kWh in the month to {date:date}. That is {pct:num}% less than you used in "
      "{month:monthname} last year, when it was {base:num} kWh. Whatever you changed is working.",
      ar="استهلكت {recent} kWh في الشهر المنتهي في {date}، أي أقل بنسبة {pct}% مما استهلكته في {month} من العام "
         "الماضي، حين كان {base} kWh. ما غيّرته يؤتي ثماره.",
      es="Consumiste {recent} kWh en el mes hasta el {date}, un {pct}% menos que en {month} del año pasado, "
         "cuando fueron {base} kWh. Lo que hayas cambiado está funcionando.",
      fr="Vous avez consommé {recent} kWh sur le mois se terminant le {date}, soit {pct} % de moins qu’en "
         "{month} l’an dernier, où c’était {base} kWh. Ce que vous avez changé porte ses fruits.",
      de="Sie haben im Monat bis zum {date} {recent} kWh verbraucht, {pct} % weniger als im {month} des "
         "Vorjahres, als es {base} kWh waren. Was Sie geändert haben, wirkt.",
      zh="截至 {date} 的一个月内，您用电 {recent} kWh，比去年 {month} 的 {base} kWh 低 {pct}%。"
         "您做出的改变见效了。",
      ja="{date}までの1か月の使用量は{recent} kWhで、昨年{month}の{base} kWhより{pct}%少なくなっています。"
         "変えたことが効果を上げています。"),
    M("You used {recent:num} kWh in the month to {date:date}. That is {pct:num}% less than the average of "
      "your recent months, which was {base:num} kWh. Until you have a year of history, that is the best "
      "comparison available. Whatever you changed is working.",
      ar="استهلكت {recent} kWh في الشهر المنتهي في {date}، أي أقل بنسبة {pct}% من متوسط أشهرك الأخيرة، الذي كان "
         "{base} kWh. وإلى أن يتوفّر لديك سجلّ لعام كامل، فهذه أفضل مقارنة متاحة. ما غيّرته يؤتي ثماره.",
      es="Consumiste {recent} kWh en el mes hasta el {date}, un {pct}% menos que la media de tus últimos "
         "meses, que era de {base} kWh. Hasta que tengas un año de historial, es la mejor comparación posible. "
         "Lo que hayas cambiado está funcionando.",
      fr="Vous avez consommé {recent} kWh sur le mois se terminant le {date}, soit {pct} % de moins que la "
         "moyenne de vos derniers mois, qui était de {base} kWh. Tant que vous n’avez pas un an d’historique, "
         "c’est la meilleure comparaison possible. Ce que vous avez changé porte ses fruits.",
      de="Sie haben im Monat bis zum {date} {recent} kWh verbraucht, {pct} % weniger als der Durchschnitt "
         "Ihrer letzten Monate, der bei {base} kWh lag. Solange Sie keine Jahreshistorie haben, ist das der "
         "beste verfügbare Vergleich. Was Sie geändert haben, wirkt.",
      zh="截至 {date} 的一个月内，您用电 {recent} kWh，比您最近几个月的平均值 {base} kWh 低 {pct}%。"
         "在您有满一年的记录之前，这是能做的最佳比较。您做出的改变见效了。",
      ja="{date}までの1か月の使用量は{recent} kWhで、直近数か月の平均{base} kWhより{pct}%少なくなっています。"
         "1年分の履歴がそろうまでは、これが最も適切な比較です。変えたことが効果を上げています。"),

    # ------------------------------------------------------------------
    # app/ai/alerts.py: bill messages
    # ------------------------------------------------------------------
    M("1 unpaid bill with {owed:money} still to pay. It was due on {date:date}. Please settle it to avoid "
      "a service interruption.",
      ar="فاتورة واحدة غير مدفوعة، والمتبقي عليها {owed}. كان موعد استحقاقها {date}. يُرجى تسديدها لتجنّب "
         "انقطاع الخدمة.",
      es="1 factura sin pagar con {owed} pendientes. Vencía el {date}. Págala para evitar un corte del servicio.",
      fr="1 facture impayée avec {owed} restant à payer. Elle était due le {date}. Merci de la régler pour "
         "éviter une interruption du service.",
      de="1 offene Rechnung, noch {owed} zu zahlen. Sie war am {date} fällig. Bitte begleichen Sie sie, um "
         "eine Unterbrechung der Versorgung zu vermeiden.",
      zh="您有 1 张未付账单，尚需支付 {owed}。该账单已于 {date} 到期。请尽快缴清，以免中断供电。",
      ja="未払いの請求書が1件あり、残り{owed}のお支払いが必要です。支払期限は{date}でした。供給停止を避けるため、"
         "お支払いください。"),
    M("{n:num} unpaid bills with {owed:money} still to pay. The oldest was due on {date:date}. Please settle "
      "them to avoid a service interruption.",
      ar="عدد الفواتير غير المدفوعة: {n}، والمتبقي عليها {owed}. كان موعد استحقاق أقدمها {date}. يُرجى تسديدها "
         "لتجنّب انقطاع الخدمة.",
      es="{n} facturas sin pagar con {owed} pendientes. La más antigua vencía el {date}. Págalas para evitar "
         "un corte del servicio.",
      fr="{n} factures impayées avec {owed} restant à payer. La plus ancienne était due le {date}. Merci de "
         "les régler pour éviter une interruption du service.",
      de="{n} offene Rechnungen, noch {owed} zu zahlen. Die älteste war am {date} fällig. Bitte begleichen Sie "
         "sie, um eine Unterbrechung der Versorgung zu vermeiden.",
      zh="您有 {n} 张未付账单，尚需支付 {owed}。最早的一张已于 {date} 到期。请尽快缴清，以免中断供电。",
      ja="未払いの請求書が{n}件あり、残り{owed}のお支払いが必要です。最も古いものの支払期限は{date}でした。"
         "供給停止を避けるため、お支払いください。"),
    M("Your {month:monthyear} bill is due on {date:date}, with {owed:money} to pay.",
      ar="تستحق فاتورة {month} في {date}، والمبلغ المطلوب {owed}.",
      es="Tu factura de {month} vence el {date}; importe a pagar: {owed}.",
      fr="Votre facture de {month} est due le {date} ; montant à payer : {owed}.",
      de="Ihre Rechnung für {month} ist am {date} fällig; zu zahlen: {owed}.",
      zh="您 {month} 的账单将于 {date} 到期，应付 {owed}。",
      ja="{month}分の請求書の支払期限は{date}です。お支払い額は{owed}です。"),
    M("Your {month:monthyear} bill is due on {date:date}, with {owed:money} still to pay of {total:money}.",
      ar="تستحق فاتورة {month} في {date}، والمتبقي منها {owed} من أصل {total}.",
      es="Tu factura de {month} vence el {date}; quedan {owed} por pagar de {total}.",
      fr="Votre facture de {month} est due le {date} ; il reste {owed} à payer sur {total}.",
      de="Ihre Rechnung für {month} ist am {date} fällig; offen sind noch {owed} von {total}.",
      zh="您 {month} 的账单将于 {date} 到期，{total} 中尚有 {owed} 未付。",
      ja="{month}分の請求書の支払期限は{date}です。{total}のうち{owed}が未払いです。"),

    # ------------------------------------------------------------------
    # app/ai/alerts.py: anomaly messages
    # ------------------------------------------------------------------
    M("Your monthly readings up to {date:date} stand out against those of similar accounts. If this does "
      "not match how you used electricity, contact support so the meter can be checked.",
      ar="تختلف قراءاتك الشهرية حتى {date} عن قراءات الحسابات المشابهة. إذا لم يتوافق ذلك مع طريقة استخدامك "
         "للكهرباء، فتواصل مع الدعم لفحص العدّاد.",
      es="Tus lecturas mensuales hasta el {date} se apartan de las de cuentas similares. Si no coincide con tu "
         "uso de la electricidad, contacta con soporte para que revisen el contador.",
      fr="Vos relevés mensuels jusqu’au {date} se distinguent de ceux de comptes comparables. Si cela ne "
         "correspond pas à votre usage de l’électricité, contactez le support pour faire vérifier le compteur.",
      de="Ihre monatlichen Zählerstände bis zum {date} weichen von denen vergleichbarer Konten ab. Wenn das "
         "nicht zu Ihrem Stromverbrauch passt, wenden Sie sich an den Support, damit der Zähler geprüft wird.",
      zh="截至 {date}，您的月度读数与同类账户明显不同。如与您的实际用电情况不符，请联系客服检查电表。",
      ja="{date}までの毎月の検針値が、同様の契約と比べて目立って異なっています。電気の使い方と合わない場合は、"
         "メーターを点検できるようサポートにお問い合わせください。"),
    M("{description:sub} Recorded on {date:date}. If this does not match what you were doing, contact support.",
      ar="{description} سُجّلت في {date}. إذا لم يتوافق ذلك مع ما كنت تفعله، فتواصل مع الدعم.",
      es="{description} Registrado el {date}. Si no coincide con lo que estabas haciendo, contacta con soporte.",
      fr="{description} Enregistré le {date}. Si cela ne correspond pas à ce que vous faisiez, contactez le support.",
      de="{description} Erfasst am {date}. Wenn das nicht zu Ihrem Verbrauch passt, wenden Sie sich an den Support.",
      zh="{description}记录于 {date}。如与您的实际用电情况不符，请联系客服。",
      ja="{description}記録日：{date}。心当たりがない場合はサポートにお問い合わせください。"),
    M("{n:num} unusual readings in the last {days:num} days, the most recent on {date:date}. "
      "{description:sub} If this does not match what you were doing, contact support.",
      ar="عدد القراءات غير الاعتيادية خلال آخر {days} يوماً: {n}، وآخرها في {date}. {description} إذا لم يتوافق "
         "ذلك مع ما كنت تفعله، فتواصل مع الدعم.",
      es="{n} lecturas inusuales en los últimos {days} días, la más reciente el {date}. {description} Si no "
         "coincide con lo que estabas haciendo, contacta con soporte.",
      fr="{n} relevés inhabituels sur les {days} derniers jours, le plus récent le {date}. {description} Si "
         "cela ne correspond pas à ce que vous faisiez, contactez le support.",
      de="{n} ungewöhnliche Zählerstände in den letzten {days} Tagen, der jüngste am {date}. {description} "
         "Wenn das nicht zu Ihrem Verbrauch passt, wenden Sie sich an den Support.",
      zh="过去 {days} 天内有 {n} 次异常读数，最近一次在 {date}。{description}如与您的实际用电情况不符，请联系客服。",
      ja="直近{days}日間に異常な検針値が{n}件あり、最新は{date}です。{description}心当たりがない場合はサポートに"
         "お問い合わせください。"),

    # ------------------------------------------------------------------
    # app/ai/anomaly.py: types (shown inside sentences; the anomaly page
    # translates the type itself) and day-level descriptions
    # ------------------------------------------------------------------
    M("Unusual Monthly Profile",
      ar="نمط شهري غير اعتيادي", es="Perfil mensual inusual", fr="Profil mensuel inhabituel",
      de="Ungewöhnliches Monatsprofil", zh="月度用电模式异常", ja="月次パターンの異常"),
    M("Meter Error",
      ar="خطأ في العدّاد", es="Error del contador", fr="Erreur de compteur",
      de="Zählerfehler", zh="电表故障", ja="メーターの異常"),
    M("Possible Fraud",
      ar="احتمال تلاعب", es="Posible fraude", fr="Fraude possible",
      de="Möglicher Betrug", zh="疑似违规用电", ja="不正の可能性"),
    M("Abnormal Spike",
      ar="ارتفاع حادّ غير طبيعي", es="Pico anómalo", fr="Pic anormal",
      de="Ungewöhnliche Spitze", zh="异常激增", ja="異常な急増"),
    M("Unusual Consumption",
      ar="استهلاك غير اعتيادي", es="Consumo inusual", fr="Consommation inhabituelle",
      de="Ungewöhnlicher Verbrauch", zh="用电异常", ja="異常な消費"),
    M("No readings received for an extended period. Possible hardware or communication fault at the meter.",
      ar="لم تصل أي قراءات لفترة طويلة. قد يكون هناك عطل في العدّاد أو في الاتصال به.",
      es="No se han recibido lecturas durante un periodo prolongado. Posible fallo de hardware o de "
         "comunicación en el contador.",
      fr="Aucun relevé reçu depuis longtemps. Panne matérielle ou de communication possible au compteur.",
      de="Seit längerer Zeit sind keine Zählerstände eingegangen. Möglicher Hardware- oder "
         "Kommunikationsfehler am Zähler.",
      zh="长时间未收到读数，电表可能存在硬件或通信故障。",
      ja="長期間検針値が届いていません。メーターのハードウェアまたは通信の不具合の可能性があります。"),
    M("Reported usage dropped sharply against the customer's established baseline, a known meter-tampering "
      "signature. Recommend field inspection.",
      ar="انخفض الاستهلاك المسجَّل بشكل حادّ مقارنةً بالمستوى المعتاد للعميل، وهو نمط معروف للعبث بالعدّادات. "
         "يُنصح بالكشف الميداني.",
      es="El consumo registrado cayó bruscamente respecto a la línea base habitual del cliente, un patrón "
         "conocido de manipulación del contador. Se recomienda inspección en campo.",
      fr="La consommation relevée a chuté nettement par rapport au niveau habituel du client, une signature "
         "connue de manipulation de compteur. Inspection sur place recommandée.",
      de="Der gemeldete Verbrauch ist gegenüber dem üblichen Niveau des Kunden stark gefallen, ein bekanntes "
         "Muster für Zählermanipulation. Vor-Ort-Prüfung empfohlen.",
      zh="上报的用电量较该客户的正常基线大幅下降，这是已知的电表篡改特征，建议现场检查。",
      ja="報告された使用量が顧客のいつもの水準から急落しています。メーター改ざんの既知のパターンです。"
         "現地点検を推奨します。"),
    M("Consumption rose {pct:num}% above the 30-day rolling baseline within a short window. Possible "
      "appliance fault or unreported load.",
      ar="ارتفع الاستهلاك بنسبة {pct}% فوق متوسط آخر 30 يوماً خلال فترة قصيرة. قد يكون هناك عطل في جهاز أو "
         "حِمل غير مُبلَّغ عنه.",
      es="El consumo subió un {pct}% por encima de la media móvil de 30 días en poco tiempo. Posible fallo "
         "de un aparato o carga no declarada.",
      fr="La consommation a dépassé de {pct} % la moyenne glissante sur 30 jours en peu de temps. Panne "
         "d’appareil ou charge non déclarée possible.",
      de="Der Verbrauch stieg in kurzer Zeit um {pct} % über den gleitenden 30-Tage-Durchschnitt. Möglicher "
         "Gerätefehler oder nicht gemeldete Last.",
      zh="用电量在短时间内比 30 天滚动基线高出 {pct}%，可能是电器故障或未申报的负荷。",
      ja="短期間で使用量が30日移動平均を{pct}%上回りました。機器の故障または未申告の負荷の可能性があります。"),
    M("Consumption deviates {pct:num}% from this customer's normal pattern, detected by the AI model.",
      ar="ينحرف الاستهلاك بنسبة {pct}% عن النمط المعتاد لهذا العميل، بحسب نموذج الذكاء الاصطناعي.",
      es="El consumo se desvía un {pct}% del patrón normal de este cliente, según el modelo de IA.",
      fr="La consommation s’écarte de {pct} % du profil habituel de ce client, d’après le modèle d’IA.",
      de="Der Verbrauch weicht laut KI-Modell um {pct} % vom üblichen Muster dieses Kunden ab.",
      zh="AI 模型检测到，该客户的用电偏离其正常模式 {pct}%。",
      ja="AIモデルによると、使用量がこの顧客の通常パターンから{pct}%ずれています。"),
    M("{rank:num} of {total:num}",
      ar="{rank} من {total}", es="{rank} de {total}", fr="{rank} sur {total}",
      de="{rank} von {total}", zh="第 {rank} / 共 {total}", ja="{total}件中{rank}位"),

    # ------------------------------------------------------------------
    # app/ai/subscriber_anomaly.py: why a subscriber stands out. Each clause
    # is "<feature> is unusually high|low (<name>=<value>)"; clauses are
    # joined with "; ", which localize() splits.
    # ------------------------------------------------------------------
    M("{feature:sub} is unusually high ({value:expr})",
      ar="{feature}: مرتفع بشكل غير اعتيادي ({value})",
      es="{feature}: valor inusualmente alto ({value})",
      fr="{feature} : valeur anormalement élevée ({value})",
      de="{feature}: ungewöhnlich hoch ({value})",
      zh="{feature}异常偏高（{value}）",
      ja="{feature}が異常に高い（{value}）"),
    M("{feature:sub} is unusually low ({value:expr})",
      ar="{feature}: منخفض بشكل غير اعتيادي ({value})",
      es="{feature}: valor inusualmente bajo ({value})",
      fr="{feature} : valeur anormalement basse ({value})",
      de="{feature}: ungewöhnlich niedrig ({value})",
      zh="{feature}异常偏低（{value}）",
      ja="{feature}が異常に低い（{value}）"),
    M("how much this subscriber uses at all",
      ar="مقدار ما يستهلكه هذا المشترك أصلاً", es="cuánto consume este abonado",
      fr="le volume consommé par cet abonné", de="wie viel dieser Abonnent überhaupt verbraucht",
      zh="该用户的总体用电量", ja="この契約者の使用量そのもの"),
    M("how unstable that use is month to month",
      ar="مدى تقلّب هذا الاستهلاك من شهر إلى آخر", es="lo inestable que es ese consumo de un mes a otro",
      fr="l’instabilité de cette consommation d’un mois à l’autre",
      de="wie stark dieser Verbrauch von Monat zu Monat schwankt", zh="逐月用电的波动程度",
      ja="月ごとの使用量の不安定さ"),
    M("whether it drifted up or down across the record",
      ar="ما إذا كان قد اتجه صعوداً أو هبوطاً على مدى السجل", es="si subió o bajó a lo largo del registro",
      fr="sa tendance à la hausse ou à la baisse sur l’historique",
      de="ob er über den Zeitraum gestiegen oder gesunken ist", zh="整个记录期间的上升或下降趋势",
      ja="記録期間を通じた増減の傾向"),
    M("the deepest single-month fall",
      ar="أكبر انخفاض في شهر واحد", es="la mayor caída en un solo mes",
      fr="la plus forte baisse sur un seul mois", de="der stärkste Rückgang in einem einzelnen Monat",
      zh="单月最大降幅", ja="1か月での最大の落ち込み"),
    M("whether a fall persisted rather than rebounding",
      ar="ما إذا استمرّ الانخفاض بدل أن يعود إلى مستواه", es="si una caída se mantuvo en lugar de recuperarse",
      fr="si une baisse a persisté au lieu de rebondir", de="ob ein Rückgang anhielt, statt sich zu erholen",
      zh="下降是否持续而未回升", ja="落ち込みが回復せずに続いたかどうか"),
    M("months the dial did not move",
      ar="الأشهر التي لم يتحرّك فيها العدّاد", es="meses en que el contador no se movió",
      fr="les mois où le compteur n’a pas bougé", de="Monate, in denen sich der Zähler nicht bewegt hat",
      zh="电表读数不动的月数", ja="メーターが動かなかった月数"),
    M("the longest run of identical readings",
      ar="أطول سلسلة من القراءات المتطابقة", es="la racha más larga de lecturas idénticas",
      fr="la plus longue série de relevés identiques", de="die längste Folge identischer Zählerstände",
      zh="连续相同读数的最长次数", ja="同一検針値が続いた最長期間"),
    M("how well the readings could be recognised",
      ar="مدى وضوح القراءات عند التعرّف عليها", es="lo bien que se pudieron reconocer las lecturas",
      fr="la qualité de reconnaissance des relevés", de="wie gut die Zählerstände erkannt werden konnten",
      zh="读数识别的清晰程度", ja="検針値の読み取りやすさ"),
    M("how often a reading needed correcting by hand",
      ar="عدد المرّات التي احتاجت فيها القراءة إلى تصحيح يدوي",
      es="con qué frecuencia hubo que corregir una lectura a mano",
      fr="la fréquence des corrections manuelles de relevés",
      de="wie oft ein Zählerstand von Hand korrigiert werden musste", zh="读数需要人工更正的频率",
      ja="検針値を手作業で修正した頻度"),
    M("use against the capacity actually contracted",
      ar="الاستهلاك مقارنةً بالقدرة المتعاقد عليها فعلياً", es="el consumo frente a la potencia contratada",
      fr="la consommation rapportée à la puissance souscrite",
      de="der Verbrauch im Verhältnis zur vertraglichen Leistung", zh="用电量与实际签约容量之比",
      ja="契約容量に対する使用量"),
    M("use against neighbours on the same feeder, same weather, same tariff",
      ar="الاستهلاك مقارنةً بالجيران على الخط نفسه، مع الطقس والتعرفة نفسيهما",
      es="el consumo frente a los vecinos de la misma línea, con el mismo clima y la misma tarifa",
      fr="la consommation comparée aux voisins sur la même ligne, même météo, même tarif",
      de="der Verbrauch im Vergleich zu Nachbarn am selben Strang, bei gleichem Wetter und Tarif",
      zh="与同一线路、同样天气和电价的邻居相比的用电量", ja="同じ配電線・同じ天候・同じ料金の近隣と比べた使用量"),
    M("months read while the account was marked disconnected",
      ar="الأشهر التي قُرئ فيها العدّاد بينما كان الحساب مسجّلاً كمفصول",
      es="meses leídos mientras la cuenta figuraba como desconectada",
      fr="les mois relevés alors que le compte était noté comme déconnecté",
      de="Monate mit Ablesung, obwohl das Konto als abgeschaltet geführt war",
      zh="账户标记为断开期间仍有读数的月数", ja="契約が切断扱いの間に検針された月数"),
    M("no single feature stands out; the combination does",
      ar="لا تبرز أي سمة بمفردها، بل اجتماعها", es="ninguna característica destaca por sí sola; lo hace la combinación",
      fr="aucune caractéristique ne ressort seule ; c’est leur combinaison qui ressort",
      de="kein einzelnes Merkmal fällt auf, wohl aber die Kombination",
      zh="没有单一特征突出，是多个特征的组合导致", ja="単独で目立つ特徴はなく、組み合わせが目立っています"),

    # ------------------------------------------------------------------
    # app/ai/risk.py: reasons beside a payment-risk score
    # ------------------------------------------------------------------
    M("{owed:money} outstanding, {ratio:num}x a typical bill",
      ar="{owed} متبقٍّ، أي {ratio} ضعف الفاتورة المعتادة",
      es="{owed} pendientes, {ratio} veces una factura habitual",
      fr="{owed} restant dû, soit {ratio} fois une facture habituelle",
      de="{owed} offen, das {ratio}-Fache einer üblichen Rechnung",
      zh="未付 {owed}，是平常账单的 {ratio} 倍",
      ja="未払い{owed}（通常の請求額の{ratio}倍）"),
    M("Pays {n:num} days late on average",
      ar=Plural("n", one="يدفع متأخراً يوماً واحداً في المتوسط", two="يدفع متأخراً يومين في المتوسط",
                few="يدفع متأخراً {n} أيام في المتوسط", many="يدفع متأخراً {n} يوماً في المتوسط",
                other="يدفع متأخراً {n} يوم في المتوسط"),
      es="Paga con {n} días de retraso de media",
      fr="Paie avec {n} jours de retard en moyenne",
      de="Zahlt im Schnitt {n} Tage zu spät",
      zh="平均逾期 {n} 天付款",
      ja="平均{n}日遅れて支払い"),
    M("1 bill with nothing paid against it",
      ar="فاتورة واحدة لم يُدفع منها شيء", es="1 factura sin ningún pago", fr="1 facture sans aucun paiement",
      de="1 Rechnung ohne jede Zahlung", zh="1 张账单分文未付", ja="支払いが一切ない請求書が1件"),
    M("{n:num} bills with nothing paid against them",
      ar="عدد الفواتير التي لم يُدفع منها شيء: {n}", es="{n} facturas sin ningún pago",
      fr="{n} factures sans aucun paiement", de="{n} Rechnungen ohne jede Zahlung",
      zh="{n} 张账单分文未付", ja="支払いが一切ない請求書が{n}件"),
    M("1 part-paid bill still carrying a balance",
      ar="فاتورة واحدة مدفوعة جزئياً وما زال عليها رصيد", es="1 factura pagada en parte con saldo pendiente",
      fr="1 facture partiellement payée avec un solde restant", de="1 teilweise bezahlte Rechnung mit offenem Rest",
      zh="1 张部分付款的账单仍有余额", ja="一部支払い済みで残高のある請求書が1件"),
    M("{n:num} part-paid bills still carrying a balance",
      ar="عدد الفواتير المدفوعة جزئياً وما زال عليها رصيد: {n}",
      es="{n} facturas pagadas en parte con saldo pendiente",
      fr="{n} factures partiellement payées avec un solde restant",
      de="{n} teilweise bezahlte Rechnungen mit offenem Rest",
      zh="{n} 张部分付款的账单仍有余额", ja="一部支払い済みで残高のある請求書が{n}件"),
    M("No payment received for {n:num} days",
      ar=Plural("n", one="لم تصل أي دفعة منذ يوم واحد", two="لم تصل أي دفعة منذ يومين",
                few="لم تصل أي دفعة منذ {n} أيام", many="لم تصل أي دفعة منذ {n} يوماً",
                other="لم تصل أي دفعة منذ {n} يوم"),
      es="Sin pagos desde hace {n} días", fr="Aucun paiement reçu depuis {n} jours",
      de="Seit {n} Tagen keine Zahlung eingegangen", zh="已 {n} 天未收到付款", ja="{n}日間入金がありません"),
    M("No payment has ever been received",
      ar="لم تصل أي دفعة على الإطلاق", es="Nunca se ha recibido un pago", fr="Aucun paiement n’a jamais été reçu",
      de="Es ist noch nie eine Zahlung eingegangen", zh="从未收到过付款", ja="これまで入金が一度もありません"),
    M("Account is currently suspended",
      ar="الحساب موقوف حالياً", es="La cuenta está suspendida", fr="Le compte est actuellement suspendu",
      de="Das Konto ist derzeit gesperrt", zh="账户目前已暂停", ja="契約は現在停止中です"),
    M("Pays on time with nothing outstanding",
      ar="يدفع في الموعد ولا شيء متبقٍّ عليه", es="Paga a tiempo y no debe nada", fr="Paie à temps, rien de dû",
      de="Zahlt pünktlich, nichts offen", zh="按时付款，无欠款", ja="期限どおりに支払い、未払いなし"),
    M("No billing history yet, not enough evidence to score.",
      ar="لا يوجد سجل فوترة بعد، ولا تكفي الأدلة لاحتساب الدرجة.",
      es="Aún no hay historial de facturación; no hay datos suficientes para puntuar.",
      fr="Pas encore d’historique de facturation : trop peu d’éléments pour noter.",
      de="Noch keine Abrechnungshistorie, zu wenig Anhaltspunkte für eine Bewertung.",
      zh="尚无账单记录，证据不足，无法评分。", ja="請求履歴がまだなく、評価する根拠が足りません。"),

    # ------------------------------------------------------------------
    # app/routers/dashboard.py: the administrator's activity feed
    # ------------------------------------------------------------------
    M("New customer {name} registered",
      ar="تسجيل عميل جديد: {name}", es="Nuevo cliente registrado: {name}", fr="Nouveau client inscrit : {name}",
      de="Neuer Kunde registriert: {name}", zh="新客户注册：{name}", ja="新規顧客が登録：{name}"),
    M("Payment of {amount:money} processed for {customer}",
      ar="تمت معالجة دفعة بقيمة {amount} للحساب {customer}", es="Pago de {amount} procesado para {customer}",
      fr="Paiement de {amount} traité pour {customer}", de="Zahlung über {amount} für {customer} verbucht",
      zh="已为 {customer} 处理一笔 {amount} 的付款", ja="{customer}の{amount}の支払いを処理しました"),
    M("Anomaly flagged for {customer} ({kind:sub})",
      ar="رُصدت حالة غير اعتيادية للحساب {customer} ({kind})", es="Anomalía señalada para {customer} ({kind})",
      fr="Anomalie signalée pour {customer} ({kind})", de="Anomalie für {customer} gemeldet ({kind})",
      zh="{customer} 被标记异常（{kind}）", ja="{customer}に異常フラグ（{kind}）"),
    M("just now",
      ar="الآن", es="ahora mismo", fr="à l’instant", de="gerade eben", zh="刚刚", ja="たった今"),
    M("{n:num} min ago",
      ar=Plural("n", one="قبل دقيقة", two="قبل دقيقتين", few="قبل {n} دقائق", many="قبل {n} دقيقة",
                other="قبل {n} دقيقة"),
      es="hace {n} min", fr="il y a {n} min", de="vor {n} Min.", zh="{n} 分钟前", ja="{n}分前"),
    M("1 hour ago",
      ar="قبل ساعة", es="hace 1 hora", fr="il y a 1 heure", de="vor 1 Stunde", zh="1 小时前", ja="1時間前"),
    M("{n:num} hours ago",
      ar=Plural("n", one="قبل ساعة", two="قبل ساعتين", few="قبل {n} ساعات", many="قبل {n} ساعة",
                other="قبل {n} ساعة"),
      es="hace {n} horas", fr="il y a {n} heures", de="vor {n} Stunden", zh="{n} 小时前", ja="{n}時間前"),
    M("1 day ago",
      ar="قبل يوم", es="hace 1 día", fr="il y a 1 jour", de="vor 1 Tag", zh="1 天前", ja="1日前"),
    M("{n:num} days ago",
      ar=Plural("n", one="قبل يوم", two="قبل يومين", few="قبل {n} أيام", many="قبل {n} يوماً",
                other="قبل {n} يوم"),
      es="hace {n} días", fr="il y a {n} jours", de="vor {n} Tagen", zh="{n} 天前", ja="{n}日前"),

    # ------------------------------------------------------------------
    # app/ai/segmentation.py: segment descriptions (the names are
    # translated by the page, which uses them as keys)
    # ------------------------------------------------------------------
    M("{low:num}-{high:num} kWh/month",
      ar="{low}-{high} kWh شهرياً", es="{low}-{high} kWh/mes", fr="{low}-{high} kWh/mois",
      de="{low}-{high} kWh/Monat", zh="每月 {low}-{high} kWh", ja="月{low}〜{high} kWh"),
    M("~{value:num} kWh/month",
      ar="نحو {value} kWh شهرياً", es="~{value} kWh/mes", fr="~{value} kWh/mois",
      de="~{value} kWh/Monat", zh="每月约 {value} kWh", ja="月約{value} kWh"),
    M("Has at least one overdue bill",
      ar="لديه فاتورة متأخرة واحدة على الأقل", es="Tiene al menos una factura vencida",
      fr="A au moins une facture en retard", de="Hat mindestens eine überfällige Rechnung",
      zh="至少有一张逾期账单", ja="延滞中の請求書が1件以上ある"),
    M("2+ years tenure",
      ar="مشترك منذ سنتين أو أكثر", es="2 años o más como cliente", fr="Client depuis 2 ans ou plus",
      de="Seit 2 oder mehr Jahren Kunde", zh="客户时长 2 年以上", ja="契約2年以上"),

    # ------------------------------------------------------------------
    # app/routers/ishtirak.py: the loss page
    # ------------------------------------------------------------------
    M("No energy was delivered to this zone in the period shown.",
      ar="لم تُسلَّم أي طاقة إلى هذه المنطقة في الفترة المعروضة.",
      es="No se entregó energía a esta zona en el periodo mostrado.",
      fr="Aucune énergie n’a été livrée à cette zone sur la période affichée.",
      de="In diesem Zeitraum wurde keine Energie in diese Zone geliefert.",
      zh="所示期间内未向该区域供电。", ja="表示期間中、この地区への電力供給はありませんでした。"),
    M("Loses {loss:num}%, of which {unexplained:num}% is not explained by distance, load, the reading "
      "process or your own connections. Worth a visit.",
      ar="تخسر {loss}%، منها {unexplained}% لا تفسّره المسافة ولا الحِمل ولا عملية القراءة ولا توصيلاتك الخاصة. "
         "تستحق زيارة.",
      es="Pierde un {loss}%, del que un {unexplained}% no se explica por la distancia, la carga, el proceso de "
         "lectura ni tus propias conexiones. Merece una visita.",
      fr="Perd {loss} %, dont {unexplained} % ne s’expliquent ni par la distance, ni par la charge, ni par le "
         "relevé, ni par vos propres raccordements. Mérite une visite.",
      de="Verliert {loss} %, davon {unexplained} %, die weder Entfernung, Last, Ablesung noch Ihre eigenen "
         "Anschlüsse erklären. Einen Besuch wert.",
      zh="损耗 {loss}%，其中 {unexplained}% 无法用距离、负荷、抄表过程或您自己的接线解释。值得走访。",
      ja="損失は{loss}%で、そのうち{unexplained}%は距離・負荷・検針の過程・自社の接続では説明できません。"
         "訪問の価値があります。"),
    M("Loses {loss:num}%. The feeding generator is running unbalanced, which is heat in the cable serving "
      "nobody. A technician can fix this.",
      ar="تخسر {loss}%. المولّد المغذّي يعمل بأحمال غير متوازنة، ما يعني حرارة في الكابل لا تخدم أحداً. يستطيع "
         "فنّي إصلاح ذلك.",
      es="Pierde un {loss}%. El generador que la alimenta funciona desequilibrado, lo que es calor en el cable "
         "que no sirve a nadie. Un técnico puede corregirlo.",
      fr="Perd {loss} %. Le groupe qui l’alimente fonctionne en déséquilibre : c’est de la chaleur dans le "
         "câble qui ne sert à personne. Un technicien peut corriger cela.",
      de="Verliert {loss} %. Der speisende Generator läuft unsymmetrisch, das ist Wärme im Kabel, die "
         "niemandem dient. Ein Techniker kann das beheben.",
      zh="损耗 {loss}%。供电的发电机三相不平衡运行，电缆发热却无人受益。技术人员可以修复。",
      ja="損失は{loss}%です。供給元の発電機が不平衡で運転しており、誰の役にも立たない熱がケーブルで生じて"
         "います。技術者が修正できます。"),
    M("Loses {loss:num}%, and most of what is unaccounted for comes from how the meters were read rather "
      "than from where the electricity went.",
      ar="تخسر {loss}%، ومعظم ما لا يمكن احتسابه يعود إلى طريقة قراءة العدّادات لا إلى وجهة الكهرباء.",
      es="Pierde un {loss}%, y la mayor parte de lo que no cuadra se debe a cómo se leyeron los contadores y "
         "no a adónde fue la electricidad.",
      fr="Perd {loss} %, et l’essentiel de l’écart vient de la façon dont les compteurs ont été relevés "
         "plutôt que de l’endroit où est allée l’électricité.",
      de="Verliert {loss} %, und der größte Teil des Fehlbetrags stammt aus der Art der Zählerablesung, "
         "nicht aus dem Verbleib des Stroms.",
      zh="损耗 {loss}%，无法核对的部分主要来自抄表方式，而非电力的去向。",
      ja="損失は{loss}%で、説明のつかない分の大半は電力の行き先ではなく、検針の仕方によるものです。"),
    M("Loses {loss:num}%, which is what physics costs for a zone at {distance:num} m from the generator. "
      "Nothing to do.",
      ar="تخسر {loss}%، وهي كلفة الفيزياء لمنطقة تبعد {distance} م عن المولّد. لا حاجة لأي إجراء.",
      es="Pierde un {loss}%, lo que cuesta la física en una zona a {distance} m del generador. No hay nada "
         "que hacer.",
      fr="Perd {loss} %, ce que coûte la physique pour une zone à {distance} m du groupe. Rien à faire.",
      de="Verliert {loss} %, was die Physik bei einer Zone {distance} m vom Generator entfernt kostet. "
         "Nichts zu tun.",
      zh="损耗 {loss}%，这是距发电机 {distance} 米的区域的正常物理损耗，无需处理。",
      ja="損失は{loss}%で、発電機から{distance} mの地区では物理的に避けられない分です。対応は不要です。"),
    M("Loses {loss:num}%, which is what physics costs for a zone. Nothing to do.",
      ar="تخسر {loss}%، وهي كلفة الفيزياء لهذه المنطقة. لا حاجة لأي إجراء.",
      es="Pierde un {loss}%, lo que cuesta la física en esta zona. No hay nada que hacer.",
      fr="Perd {loss} %, ce que coûte la physique pour cette zone. Rien à faire.",
      de="Verliert {loss} %, was die Physik für diese Zone kostet. Nichts zu tun.",
      zh="损耗 {loss}%，属于该区域的正常物理损耗，无需处理。",
      ja="損失は{loss}%で、この地区では物理的に避けられない分です。対応は不要です。"),
    M("Total loss is {pct:num}%.",
      ar="إجمالي الخسارة {pct}%.", es="La pérdida total es del {pct}%.", fr="La perte totale est de {pct} %.",
      de="Der Gesamtverlust beträgt {pct} %.", zh="总损耗为 {pct}%。", ja="総損失は{pct}%です。"),
    M("Loss is not measurable.",
      ar="لا يمكن قياس الخسارة.", es="La pérdida no se puede medir.", fr="La perte n’est pas mesurable.",
      de="Der Verlust ist nicht messbar.", zh="损耗无法测量。", ja="損失は測定できません。"),
    M("About {pct:num}% is normal technical loss, nothing to do.",
      ar="نحو {pct}% خسارة فنية طبيعية، لا حاجة لأي إجراء.",
      es="Alrededor del {pct}% es pérdida técnica normal; no hay nada que hacer.",
      fr="Environ {pct} % sont des pertes techniques normales, rien à faire.",
      de="Etwa {pct} % sind normale technische Verluste, nichts zu tun.",
      zh="约 {pct}% 是正常的技术损耗，无需处理。", ja="約{pct}%は通常の技術損失で、対応は不要です。"),
    M("About {pct:num}% comes from the reading process, which is fixable.",
      ar="نحو {pct}% يعود إلى عملية القراءة، ويمكن تصحيحه.",
      es="Alrededor del {pct}% viene del proceso de lectura, y se puede corregir.",
      fr="Environ {pct} % viennent du relevé, ce qui se corrige.",
      de="Etwa {pct} % stammen aus der Ablesung, das lässt sich beheben.",
      zh="约 {pct}% 来自抄表过程，可以纠正。", ja="約{pct}%は検針の過程によるもので、改善できます。"),
    M("{names} is running unbalanced; send a technician.",
      ar="{names} يعمل بأحمال غير متوازنة؛ أرسِل فنياً.", es="{names} funciona desequilibrado; envía a un técnico.",
      fr="{names} fonctionne en déséquilibre ; envoyez un technicien.",
      de="{names} läuft unsymmetrisch; schicken Sie einen Techniker.",
      zh="{names} 三相不平衡运行，请派技术人员。", ja="{names}が不平衡で運転しています。技術者を派遣してください。"),
    M("{names} are running unbalanced; send a technician.",
      ar="{names} تعمل بأحمال غير متوازنة؛ أرسِل فنياً.", es="{names} funcionan desequilibrados; envía a un técnico.",
      fr="{names} fonctionnent en déséquilibre ; envoyez un technicien.",
      de="{names} laufen unsymmetrisch; schicken Sie einen Techniker.",
      zh="{names} 三相不平衡运行，请派技术人员。", ja="{names}が不平衡で運転しています。技術者を派遣してください。"),
    M("About {pct:num}% is unexplained and concentrates in {zone}. That is where a visit is worth making.",
      ar="نحو {pct}% غير مفسَّر ويتركّز في {zone}. هناك تستحق الزيارة.",
      es="Alrededor del {pct}% no tiene explicación y se concentra en {zone}. Ahí merece la pena una visita.",
      fr="Environ {pct} % restent inexpliqués et se concentrent à {zone}. C’est là qu’une visite vaut la peine.",
      de="Etwa {pct} % sind ungeklärt und konzentrieren sich auf {zone}. Dort lohnt sich ein Besuch.",
      zh="约 {pct}% 无法解释，集中在 {zone}。值得去那里走访。",
      ja="約{pct}%は説明がつかず、{zone}に集中しています。訪問するならそこです。"),

    # ------------------------------------------------------------------
    # app/analytics/rules.py: the field-visit page
    # ------------------------------------------------------------------
    M("{n:num} month(s) recorded consumption while the account was marked disconnected, {kwh:num} kWh in total",
      ar=Plural("n", one="سُجّل استهلاك خلال شهر واحد بينما كان الحساب مسجّلاً كمفصول، بإجمالي {kwh} kWh",
                two="سُجّل استهلاك خلال شهرين بينما كان الحساب مسجّلاً كمفصول، بإجمالي {kwh} kWh",
                few="سُجّل استهلاك خلال {n} أشهر بينما كان الحساب مسجّلاً كمفصول، بإجمالي {kwh} kWh",
                many="سُجّل استهلاك خلال {n} شهراً بينما كان الحساب مسجّلاً كمفصول، بإجمالي {kwh} kWh",
                other="سُجّل استهلاك خلال {n} شهر بينما كان الحساب مسجّلاً كمفصول، بإجمالي {kwh} kWh"),
      es="{n} mes(es) con consumo registrado mientras la cuenta figuraba como desconectada, {kwh} kWh en total",
      fr="{n} mois avec une consommation relevée alors que le compte était noté comme déconnecté, {kwh} kWh au total",
      de="{n} Monat(e) mit erfasstem Verbrauch, obwohl das Konto als abgeschaltet geführt war, insgesamt {kwh} kWh",
      zh="账户标记为断开期间有 {n} 个月记录到用电，共 {kwh} kWh",
      ja="契約が切断扱いの間に{n}か月分の使用が記録され、合計{kwh} kWh"),
    M("identical reading for {n:num} consecutive months",
      ar=Plural("n", one="قراءة متطابقة لشهر واحد", two="قراءة متطابقة لشهرين متتاليين",
                few="قراءة متطابقة لـ{n} أشهر متتالية", many="قراءة متطابقة لـ{n} شهراً متتالياً",
                other="قراءة متطابقة لـ{n} شهر متتالٍ"),
      es="lectura idéntica durante {n} meses seguidos", fr="relevé identique pendant {n} mois consécutifs",
      de="identischer Zählerstand {n} Monate in Folge", zh="连续 {n} 个月读数相同", ja="{n}か月連続で同じ検針値"),
    M("reading fell by {drop:num} in {month:monthyear}, which a {digits:num}-digit rollover does not explain",
      ar="انخفضت القراءة بمقدار {drop} في {month}، ولا يفسّر ذلك عودة عدّاد من {digits} خانات إلى الصفر",
      es="la lectura bajó {drop} en {month}, algo que no explica el paso por cero de un contador de {digits} dígitos",
      fr="le relevé a baissé de {drop} en {month}, ce qu’un retour à zéro d’un compteur à {digits} chiffres "
         "n’explique pas",
      de="der Zählerstand fiel im {month} um {drop}, was ein Überlauf eines {digits}-stelligen Zählers nicht erklärt",
      zh="{month} 读数下降 {drop}，{digits} 位电表归零无法解释",
      ja="{month}に検針値が{drop}下がりました。{digits}桁メーターの桁あふれでは説明できません"),
    M("used {used:num} kWh in {month:monthyear} against a {amps:num} A limit that allows at most {cap:num} kWh "
      "over the hours that zone was supplied",
      ar="استهلك {used} kWh في {month} مقابل حدّ {amps} أمبير لا يسمح بأكثر من {cap} kWh خلال ساعات تغذية المنطقة",
      es="consumió {used} kWh en {month} con un límite de {amps} A que permite como máximo {cap} kWh en las "
         "horas en que la zona tuvo suministro",
      fr="a consommé {used} kWh en {month} pour une limite de {amps} A qui permet au plus {cap} kWh sur les "
         "heures où la zone était alimentée",
      de="verbrauchte im {month} {used} kWh bei einer Grenze von {amps} A, die in den Versorgungsstunden der "
         "Zone höchstens {cap} kWh zulässt",
      zh="{month} 用电 {used} kWh，而 {amps} A 的限额在该区域供电时数内最多允许 {cap} kWh",
      ja="{month}に{used} kWhを使用。{amps} Aの上限では、その地区の供給時間内で最大{cap} kWhまでです"),
    M("average monthly use fell from {before:num} kWh to {after:num} kWh, down {drop:num}%, and stayed down",
      ar="انخفض متوسط الاستهلاك الشهري من {before} kWh إلى {after} kWh، أي بنسبة {drop}%، وبقي منخفضاً",
      es="el consumo medio mensual bajó de {before} kWh a {after} kWh, un {drop}% menos, y se mantuvo bajo",
      fr="la consommation mensuelle moyenne est passée de {before} kWh à {after} kWh, soit {drop} % de moins, "
         "et est restée basse",
      de="der durchschnittliche Monatsverbrauch fiel von {before} kWh auf {after} kWh, um {drop} %, und blieb niedrig",
      zh="月均用电从 {before} kWh 降至 {after} kWh，下降 {drop}%，且持续偏低",
      ja="月平均使用量が{before} kWhから{after} kWhへ{drop}%減少し、そのまま低い状態です"),
    M("average imbalance {imbalance:num}% against a {threshold:num}% threshold, above it for {hours:num}% of "
      "running hours",
      ar="متوسط عدم التوازن {imbalance}% مقابل عتبة {threshold}%، وتجاوزها في {hours}% من ساعات التشغيل",
      es="desequilibrio medio del {imbalance}% frente a un umbral del {threshold}%, por encima durante el "
         "{hours}% de las horas de funcionamiento",
      fr="déséquilibre moyen de {imbalance} % pour un seuil de {threshold} %, dépassé pendant {hours} % des "
         "heures de fonctionnement",
      de="durchschnittliche Unsymmetrie {imbalance} % bei einer Schwelle von {threshold} %, in {hours} % der "
         "Betriebsstunden darüber",
      zh="平均不平衡度 {imbalance}%（阈值 {threshold}%），{hours}% 的运行时间超过阈值",
      ja="平均不平衡率{imbalance}%（基準{threshold}%）、運転時間の{hours}%で基準超過"),
    M("litres per kWh rose from {early:num} to {late:num}, up {rise:num}%",
      ar="ارتفع عدد الليترات لكل kWh من {early} إلى {late}، أي بنسبة {rise}%",
      es="los litros por kWh subieron de {early} a {late}, un {rise}% más",
      fr="les litres par kWh sont passés de {early} à {late}, soit {rise} % de plus",
      de="Liter pro kWh stiegen von {early} auf {late}, um {rise} %",
      zh="每 kWh 耗油从 {early} 升增至 {late} 升，上升 {rise}%",
      ja="kWhあたりの燃料が{early}リットルから{late}リットルへ{rise}%増加"),
    M("the disconnection was never carried out in the field",
      ar="لم يُنفَّذ الفصل فعلياً على الأرض", es="la desconexión nunca se llevó a cabo sobre el terreno",
      fr="la déconnexion n’a jamais été effectuée sur le terrain", de="die Abschaltung wurde vor Ort nie durchgeführt",
      zh="现场从未实际断开", ja="現地で切断が実施されていなかった"),
    M("the status was recorded late or in error",
      ar="سُجّلت الحالة متأخرة أو عن طريق الخطأ", es="el estado se registró tarde o por error",
      fr="le statut a été enregistré tardivement ou par erreur", de="der Status wurde zu spät oder irrtümlich erfasst",
      zh="状态登记延迟或有误", ja="状態の記録が遅れたか誤っていた"),
    M("the property is empty",
      ar="العقار خالٍ", es="la vivienda está vacía", fr="le logement est vide", de="die Wohnung steht leer",
      zh="房屋空置", ja="物件が空き家になっている"),
    M("the meter has failed and needs replacing",
      ar="العدّاد معطّل ويحتاج إلى استبدال", es="el contador ha fallado y hay que cambiarlo",
      fr="le compteur est en panne et doit être remplacé", de="der Zähler ist defekt und muss ersetzt werden",
      zh="电表故障，需要更换", ja="メーターが故障しており交換が必要"),
    M("the meter was replaced and the new one started from zero",
      ar="استُبدل العدّاد وبدأ الجديد من الصفر", es="se cambió el contador y el nuevo empezó desde cero",
      fr="le compteur a été remplacé et le nouveau est reparti de zéro",
      de="der Zähler wurde getauscht und der neue begann bei null",
      zh="电表已更换，新表从零开始计数", ja="メーターが交換され、新しいメーターがゼロから始まった"),
    M("the reading was mistyped or misread",
      ar="أُدخلت القراءة أو قُرئت بشكل خاطئ", es="la lectura se tecleó o se leyó mal",
      fr="le relevé a été mal saisi ou mal lu", de="der Zählerstand wurde falsch eingegeben oder abgelesen",
      zh="读数录入或识读有误", ja="検針値の入力ミスまたは読み間違い"),
    M("the contracted capacity on record is out of date",
      ar="القدرة المتعاقد عليها في السجل لم تعد محدّثة", es="la potencia contratada registrada está desactualizada",
      fr="la puissance souscrite enregistrée n’est plus à jour", de="die hinterlegte Vertragsleistung ist veraltet",
      zh="记录中的签约容量已过时", ja="記録上の契約容量が古い"),
    M("two properties share one meter",
      ar="عقاران يتشاركان عدّاداً واحداً", es="dos viviendas comparten un contador",
      fr="deux logements partagent un compteur", de="zwei Wohnungen teilen sich einen Zähler",
      zh="两处房屋共用一块电表", ja="2つの物件が1台のメーターを共有している"),
    M("the household travelled or the property emptied",
      ar="سافر أهل المنزل أو أُخلي العقار", es="la familia viajó o la vivienda quedó vacía",
      fr="le foyer est parti en voyage ou le logement s’est vidé",
      de="der Haushalt ist verreist oder die Wohnung wurde geräumt",
      zh="住户外出或房屋已腾空", ja="世帯が旅行に出たか、物件が空いた"),
    M("an air conditioner or water heater broke and was not replaced",
      ar="تعطّل مكيّف أو سخّان مياه ولم يُستبدل",
      es="se averió un aire acondicionado o un calentador y no se sustituyó",
      fr="un climatiseur ou un chauffe-eau est tombé en panne et n’a pas été remplacé",
      de="eine Klimaanlage oder ein Warmwasserbereiter ging kaputt und wurde nicht ersetzt",
      zh="空调或热水器坏了，没有更换", ja="エアコンや給湯器が故障し、買い替えていない"),
    M("the tenant changed",
      ar="تغيّر المستأجر", es="cambió el inquilino", fr="le locataire a changé", de="der Mieter hat gewechselt",
      zh="租户换了", ja="入居者が変わった"),
    M("a genuine effort to use less",
      ar="جهد حقيقي لتقليل الاستهلاك", es="un esfuerzo real por consumir menos",
      fr="un réel effort pour consommer moins", de="ein echtes Bemühen, weniger zu verbrauchen",
      zh="确实在努力节约用电", ja="本当に節電に取り組んでいる"),
    M("Read the dial on site and compare it with the last recorded reading.",
      ar="اقرأ العدّاد في الموقع وقارنه بآخر قراءة مسجّلة.",
      es="Lee el contador en el lugar y compáralo con la última lectura registrada.",
      fr="Relevez le compteur sur place et comparez avec le dernier relevé enregistré.",
      de="Den Zähler vor Ort ablesen und mit dem letzten erfassten Stand vergleichen.",
      zh="现场读表，并与最近一次记录的读数比较。", ja="現地でメーターを読み、最後に記録された検針値と比べる。"),
    M("Switch on a known load and watch whether the meter advances.",
      ar="شغّل حِملاً معروفاً وراقب ما إذا كان العدّاد يتقدّم.",
      es="Enciende una carga conocida y comprueba si el contador avanza.",
      fr="Branchez une charge connue et regardez si le compteur avance.",
      de="Eine bekannte Last einschalten und beobachten, ob der Zähler läuft.",
      zh="打开一个已知功率的电器，观察电表是否走字。", ja="既知の負荷をオンにして、メーターが進むか確認する。"),
    M("Read the dial on site to confirm the meter is still recording.",
      ar="اقرأ العدّاد في الموقع للتأكد من أنه ما زال يسجّل.",
      es="Lee el contador en el lugar para confirmar que sigue registrando.",
      fr="Relevez le compteur sur place pour confirmer qu’il enregistre toujours.",
      de="Den Zähler vor Ort ablesen, um zu bestätigen, dass er noch zählt.",
      zh="现场读表，确认电表仍在计量。", ja="現地でメーターを読み、まだ計量しているか確認する。"),
    M("Ask what changed in the household around the month the drop began.",
      ar="اسأل عمّا تغيّر في المنزل في الشهر الذي بدأ فيه الانخفاض.",
      es="Pregunta qué cambió en el hogar hacia el mes en que empezó la bajada.",
      fr="Demandez ce qui a changé dans le foyer vers le mois où la baisse a commencé.",
      de="Fragen, was sich im Haushalt um den Monat geändert hat, in dem der Rückgang begann.",
      zh="询问用电下降开始的那个月前后家里有什么变化。", ja="減少が始まった月ごろに家庭で何が変わったか尋ねる。"),
    M("Confirm at the pole whether the supply is physically disconnected.",
      ar="تأكّد عند العمود من أن التغذية مفصولة فعلياً.",
      es="Confirma en el poste si el suministro está físicamente desconectado.",
      fr="Vérifiez au poteau si l’alimentation est physiquement coupée.",
      de="Am Mast prüfen, ob die Versorgung physisch getrennt ist.",
      zh="在电线杆处确认是否已实际断电。", ja="電柱で供給が物理的に切断されているか確認する。"),
    M("Check the disconnection date on file against what the field team did.",
      ar="قارن تاريخ الفصل المسجّل بما نفّذه فريق الميدان.",
      es="Compara la fecha de desconexión registrada con lo que hizo el equipo de campo.",
      fr="Comparez la date de déconnexion enregistrée avec ce qu’a fait l’équipe terrain.",
      de="Das hinterlegte Abschaltdatum mit dem abgleichen, was das Außenteam getan hat.",
      zh="核对档案中的断电日期与现场人员的实际操作。", ja="記録上の切断日と現場チームの作業内容を照合する。"),
    M("Check the ampere limit on the contract against the breaker actually fitted.",
      ar="قارن حدّ الأمبير في العقد بالقاطع المركَّب فعلياً.",
      es="Compara el límite de amperios del contrato con el interruptor realmente instalado.",
      fr="Comparez la limite d’ampères du contrat avec le disjoncteur réellement installé.",
      de="Die Ampere-Grenze im Vertrag mit dem tatsächlich eingebauten Schalter vergleichen.",
      zh="核对合同中的电流限额与实际安装的断路器。", ja="契約上のアンペア上限と実際に取り付けられたブレーカーを照合する。"),
    M("Check whether more than one property is fed from this meter.",
      ar="تحقّق مما إذا كان هذا العدّاد يغذّي أكثر من عقار.",
      es="Comprueba si este contador alimenta a más de una vivienda.",
      fr="Vérifiez si plus d’un logement est alimenté par ce compteur.",
      de="Prüfen, ob mehr als eine Wohnung über diesen Zähler versorgt wird.",
      zh="检查这块电表是否给不止一处房屋供电。", ja="このメーターから複数の物件に給電していないか確認する。"),
    M("Check whether the meter was replaced, and record the new serial and its starting reading.",
      ar="تحقّق مما إذا استُبدل العدّاد، وسجّل الرقم التسلسلي الجديد وقراءته الأولى.",
      es="Comprueba si se cambió el contador y anota el nuevo número de serie y su lectura inicial.",
      fr="Vérifiez si le compteur a été remplacé et notez le nouveau numéro de série et son relevé de départ.",
      de="Prüfen, ob der Zähler getauscht wurde, und die neue Seriennummer samt Anfangsstand notieren.",
      zh="检查电表是否已更换，并记录新表编号及起始读数。",
      ja="メーターが交換されたか確認し、新しいシリアル番号と開始時の検針値を記録する。"),
    M("Re-read the dial and compare it with the figure on file.",
      ar="أعد قراءة العدّاد وقارنها بالرقم المسجّل.",
      es="Vuelve a leer el contador y compáralo con la cifra registrada.",
      fr="Relevez à nouveau le compteur et comparez avec le chiffre enregistré.",
      de="Den Zähler erneut ablesen und mit dem hinterlegten Wert vergleichen.",
      zh="重新读表，并与档案中的数字比较。", ja="メーターを読み直し、記録上の数値と比べる。"),
    M("Send a technician to balance the loads across the three phases.",
      ar="أرسِل فنياً لموازنة الأحمال على الأطوار الثلاثة.",
      es="Envía a un técnico a equilibrar las cargas entre las tres fases.",
      fr="Envoyez un technicien équilibrer les charges sur les trois phases.",
      de="Einen Techniker schicken, der die Lasten auf die drei Phasen verteilt.",
      zh="派技术人员平衡三相负荷。", ja="技術者を派遣して三相の負荷を平衡させる。"),
    M("Service the engine, and check the fuel record against deliveries.",
      ar="أجرِ صيانة للمحرّك، وقارن سجل الوقود بالكميات المسلَّمة.",
      es="Revisa el motor y compara el registro de combustible con las entregas.",
      fr="Faites réviser le moteur et comparez le registre de carburant aux livraisons.",
      de="Den Motor warten und das Kraftstoffprotokoll mit den Lieferungen abgleichen.",
      zh="保养发动机，并核对燃油记录与送货量。", ja="エンジンを整備し、燃料記録を納入量と照合する。"),
    M("A flag is a hypothesis for a field visit, not a verdict. This system cannot prove that anyone has "
      "taken anything: it reports that a pattern does not match what the data predicts and that the usual "
      "explanations do not account for it.",
      ar="العلامة فرضية تستدعي زيارة ميدانية، لا حكم نهائي. لا يستطيع هذا النظام إثبات أن أحداً أخذ شيئاً: هو يبيّن فقط أن "
         "نمطاً ما لا يطابق ما تتوقّعه البيانات وأن التفسيرات المعتادة لا تفسّره.",
      es="Una alerta es una hipótesis para una visita, no un veredicto. Este sistema no puede demostrar que "
         "nadie se haya llevado nada: indica que un patrón no coincide con lo que predicen los datos y que las "
         "explicaciones habituales no lo justifican.",
      fr="Un signalement est une hypothèse pour une visite sur place, pas un verdict. Ce système ne peut pas "
         "prouver que quelqu’un a pris quoi que ce soit : il signale qu’un schéma ne correspond pas à ce que "
         "prévoient les données et que les explications habituelles n’en rendent pas compte.",
      de="Eine Markierung ist eine Hypothese für einen Vor-Ort-Besuch, kein Urteil. Dieses System kann nicht "
         "beweisen, dass jemand etwas genommen hat: Es meldet, dass ein Muster nicht zu den Erwartungen aus "
         "den Daten passt und die üblichen Erklärungen es nicht abdecken.",
      zh="标记只是现场走访的假设，不是结论。本系统无法证明任何人拿走了任何东西：它只说明某种模式与数据的预期不符，"
         "且常见的解释无法说明它。",
      ja="フラグは現地訪問のための仮説であり、判定ではありません。このシステムは誰かが何かを持ち去ったことを証明"
         "できません。データの予測と合わないパターンがあり、通常の説明では説明がつかないことを示すだけです。"),

    # ------------------------------------------------------------------
    # app/routers/search.py: generated result titles and subtitles
    # ------------------------------------------------------------------
    M("Bill {month:monthyear}",
      ar="فاتورة {month}", es="Factura de {month}", fr="Facture de {month}", de="Rechnung {month}",
      zh="{month} 账单", ja="{month}分の請求書"),
    M("Payment {amount:money}",
      ar="دفعة {amount}", es="Pago de {amount}", fr="Paiement de {amount}", de="Zahlung über {amount}",
      zh="付款 {amount}", ja="支払い {amount}"),
    M("Saves about {amount:money} a month",
      ar="يوفّر نحو {amount} شهرياً", es="Ahorra unos {amount} al mes", fr="Fait économiser environ {amount} par mois",
      de="Spart etwa {amount} im Monat", zh="每月约节省 {amount}", ja="月に約{amount}の節約"),
]

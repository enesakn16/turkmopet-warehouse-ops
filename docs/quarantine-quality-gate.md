# Karantina veri kalitesi devre kesicisi

Hareket CSV'sindeki bozuk satırlar `--movement-quarantine-output` ile ayrı bir denetim dosyasına alınabilir. Veri kaynağındaki bozulma kabul edilebilir sınırı aşarsa mutabakatın güvenilir rapor üretmiş gibi devam etmesini engellemek için iki opsiyonel eşik kullanılabilir.

## Satır sayısı sınırı

```bash
warehouse-reconcile \
  --opening opening.csv \
  --movements movements.csv \
  --output reports/reconciliation.json \
  --movement-quarantine-output reports/quarantine.csv \
  --max-quarantined-rows 5
```

Karantinaya alınan satır sayısı 5'i aşarsa komut çıkış kodu `2` ile durur.

## Oran sınırı

```bash
warehouse-reconcile \
  --opening opening.csv \
  --movements movements.csv \
  --output reports/reconciliation.json \
  --movement-quarantine-output reports/quarantine.csv \
  --max-quarantined-rate 0.02
```

Bu örnekte karantina oranı toplam hareket satırlarının %2'sini aşarsa mutabakat durur. Oran `karantinadaki satır / toplam satır` formülüyle hesaplanır.

## Sürümlenebilir kalite profili

Otomasyonlarda aynı eşikleri her komutta tekrar yazmak yerine JSON profil kullanılabilir:

```json
{
  "max_quarantined_rows": 5,
  "max_quarantined_rate": 0.02
}
```

Profil ile çalıştırma:

```bash
warehouse-reconcile \
  --opening opening.csv \
  --movements movements.csv \
  --output reports/reconciliation.json \
  --movement-quarantine-output reports/quarantine.csv \
  --quality-profile config/production-quality.json
```

Komut satırında açıkça verilen bir eşik, yalnızca aynı profil alanını geçersiz kılar. Örneğin profil satır sınırını `5` veriyorsa `--max-quarantined-rows 2` ile o çalışmaya özel olarak daha sıkı hale getirilebilir; profilin oran sınırı korunur.

Profil güvenliği:

- Kök değer JSON nesnesi olmalıdır.
- Yalnızca `max_quarantined_rows` ve `max_quarantined_rate` alanları kabul edilir; yazım hatası olabilecek bilinmeyen alanlar reddedilir.
- Satır sınırı sıfır veya pozitif tam sayı olmalıdır.
- Oran `0` ile `1` arasında sayısal değer olmalıdır.
- Profilde en az bir eşik tanımlanmalıdır.
- Profil okunamaz veya geçersizse veri içe aktarımı başlamadan komut `2` ile durur.

## Denetim izi

Karantina açıkken başarılı biçimde üretilen mutabakat JSON'una o çalışmada gerçekten uygulanan politika da yazılır. Böylece daha sonra raporun hangi eşiklerle üretildiği geriye dönük doğrulanabilir.

Örnek:

```json
{
  "quarantine_quality_gate": {
    "profile": "production-quality.json",
    "max_quarantined_rows": 2,
    "max_quarantined_rate": 0.02,
    "valid_movement_rows": 980,
    "quarantined_movement_rows": 4,
    "quarantined_rate": 0.004065
  }
}
```

Buradaki eşikler profil dosyasındaki ham değerler değil, CLI override'ları uygulandıktan sonraki **efektif değerlerdir**. Profil alanında yalnızca dosya adı saklanır; yerel makinenin tam dosya yolu rapora sızdırılmaz.

## Güvenli davranış

- Eşik aşılırsa karantina CSV'si yine yazılır; hatalı satırlar incelenebilir.
- Mutabakat JSON'u, sorun CSV'si ve görev senkronizasyonu oluşturulmaz.
- Eşik değeri satır sayısı için sıfır veya pozitif tam sayı olmalıdır.
- Oran değeri `0` ile `1` arasında olmalıdır.
- Sınırın tam üzerindeki değer kabul edilir; yalnızca sınır aşıldığında işlem durur.
- CLI eşikleri veya kalite profili `--movement-quarantine-output` olmadan kullanılamaz.
- Başarılı rapor, uygulanan kalite politikasını ve gerçek karantina oranını kendi içinde taşır.

Önerilen üretim başlangıcı: en fazla 5 satır ve en fazla %2 karantina. Gerçek hata dağılımı ölçüldükten sonra limitler daha da sıkılaştırılmalıdır.

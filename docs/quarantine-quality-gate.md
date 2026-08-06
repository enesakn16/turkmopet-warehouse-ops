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

## Güvenli davranış

- Eşik aşılırsa karantina CSV'si yine yazılır; hatalı satırlar incelenebilir.
- Mutabakat JSON'u, sorun CSV'si ve görev senkronizasyonu oluşturulmaz.
- Eşik değeri satır sayısı için sıfır veya pozitif tam sayı olmalıdır.
- Oran değeri `0` ile `1` arasında olmalıdır.
- Sınırın tam üzerindeki değer kabul edilir; yalnızca sınır aşıldığında işlem durur.
- Kalite eşikleri `--movement-quarantine-output` olmadan kullanılamaz.

Önerilen üretim başlangıcı: en fazla 5 satır ve en fazla %2 karantina. Gerçek hata dağılımı ölçüldükten sonra limitler daha da sıkılaştırılmalıdır.

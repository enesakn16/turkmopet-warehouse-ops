# Hareket satırı karantinası

Bir hareket CSV'sindeki tek bir bozuk satırın bütün stok mutabakatını durdurması operasyonel olarak pahalıdır. Karantina modu, güvenle yorumlanabilen satırlarla mutabakata devam eder ve geçersiz satırları ayrı bir denetim dosyasına çıkarır.

## Kullanım

```bash
warehouse-reconcile \
  --opening opening.csv \
  --movements movements.csv \
  --output reports/reconciliation.json \
  --movement-quarantine-output reports/movement-quarantine.csv
```

`--movement-quarantine-output` verilmezse mevcut katı davranış korunur ve ilk hatalı satır bütün içe aktarmayı durdurur.

## Karantinaya alınan satırlar

Aşağıdaki satır hataları geçerli hareketlerden ayrılır:

- boş `event_id`
- boş `sku`
- desteklenmeyen `movement_type`
- tam sayı olmayan `quantity`
- büyük-küçük harf farkı dahil tekrarlanan `event_id`

Eksik zorunlu CSV başlıkları satır bazlı bir hata değildir. Dosyanın güvenle yorumlanması mümkün olmadığından içe aktarma hata kodu `2` ile durur.

## Çıktı şeması

```text
row_number,reason,event_id,sku,movement_type,quantity
```

Dosya UTF-8 BOM ile yazılır ve Excel'de doğrudan açılabilir. Geçersiz satırlar stok hesabına hiçbir şekilde dahil edilmez.

## Çıkış kodları

- `0`: mutabakat dengeli ve karantina boş
- `1`: mutabakat sorunu veya en az bir karantinaya alınmış hareket satırı var
- `2`: dosya, başlık ya da genel şema hatası

Karantina doluyken mutabakat dengeli görünse bile komut `1` döndürür. Bu davranış, otomasyonların eksik hareket verisini başarılı çalışma sanmasını engeller.

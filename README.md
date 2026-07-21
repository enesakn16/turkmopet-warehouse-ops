# Türkmopet Warehouse Ops

Türkmopet'in depo hareketlerini doğrulamak, mükerrer kayıtları yakalamak ve fiziksel sayım farklarını raporlamak için geliştirilen Python araçları.

## İlk modül: stok mutabakat motoru

Motor şu verileri birleştirir:

- Açılış stokları
- Mal kabul, satış, iade, transfer çıkışı ve düzeltme hareketleri
- Opsiyonel fiziksel sayım sonuçları

Ürettiği kontroller:

- Mükerrer hareket numarası
- Bilinmeyen SKU
- Geçersiz miktar
- Negatif beklenen stok
- Fiziksel sayım farkı
- Açılış listesinde olmayan sayım ürünü

## CSV ile kullanma

Paketi kur:

```bash
python -m pip install -e .
```

`opening.csv` ve opsiyonel `counted.csv` şeması:

```csv
sku,quantity
TVS-JUPITER-FILTRE,10
YAMAHA-CRYPTON-SELE-ALTI,4
```

`movements.csv` şeması:

```csv
event_id,sku,movement_type,quantity
evt-1001,TVS-JUPITER-FILTRE,RECEIPT,5
evt-1002,TVS-JUPITER-FILTRE,SALE,3
```

Desteklenen hareket tipleri: `RECEIPT`, `SALE`, `RETURN`, `TRANSFER_OUT`, `ADJUSTMENT`.

Mutabakatı çalıştır:

```bash
warehouse-reconcile \
  --opening opening.csv \
  --movements movements.csv \
  --counted counted.csv \
  --output reports/reconciliation.json \
  --issues-output reports/issues.csv
```

Komut şu çıkış kodlarını döndürür:

- `0`: stok dengeli, operasyonel sorun yok
- `1`: rapor üretildi ancak inceleme gerektiren fark veya hata var
- `2`: CSV dosyası okunamadı ya da şeması geçersiz

JSON raporu; özet, SKU satırları, beklenen stok, fiziksel sayım farkı ve yapılandırılmış sorun kayıtlarını içerir. Sorun CSV'si Excel'de doğrudan açılabilmesi için UTF-8 BOM ile yazılır.

## Python API kullanımı

```python
from warehouse_ops import Movement, MovementType, reconcile_stock

report = reconcile_stock(
    opening_stock={"TVS-JUPITER-FILTRE": 10},
    movements=[
        Movement("evt-1001", "TVS-JUPITER-FILTRE", MovementType.RECEIPT, 5),
        Movement("evt-1002", "TVS-JUPITER-FILTRE", MovementType.SALE, 3),
    ],
    counted_stock={"TVS-JUPITER-FILTRE": 12},
)

print(report.is_balanced)  # True
```

## Veri akışı

```text
CSV dışa aktarımları
        ↓
Doğrulama ve tip dönüşümü
        ↓
reconcile_stock(...)
        ↓
JSON mutabakat raporu + sorun CSV'si
```

Geçersiz veya mükerrer hareketler stok toplamına dahil edilmez; yapılandırılmış `ReconciliationIssue` kayıtları olarak döndürülür. Mükerrer SKU satırları sessizce ezilmez, import hatası olarak raporlanır.

## Geliştirme

Python 3.11 veya üzeri gerekir.

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m compileall -q warehouse_ops tests
```

CI, her push ve pull request işleminde Python 3.11, 3.12 ve 3.13 üzerinde testleri çalıştırır.

## Proje yapısı

```text
warehouse_ops/
  __init__.py
  cli.py
  io.py
  reconciliation.py
tests/
  test_io.py
  test_reconciliation.py
.github/workflows/
  python-ci.yml
```

## Yol haritası

1. Raf/kat bazlı lokasyon desteği
2. Kritik stok ve sayım farkı önceliklendirmesi
3. Shopify/İkas/Sentos dışa aktarımlarına uyarlayıcılar
4. İçe aktarma sırasında satır bazlı hata karantinası
5. Basit web paneli

## Geliştirme notu

Bu proje yapay zekâ destekli geliştirme araçlarından yararlanılarak geliştirilmektedir. Mimari kararlar, iş kuralları, doğrulama ve yayın sorumluluğu proje sahibine aittir.

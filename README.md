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

## Hızlı kullanım

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
Açılış stoku + hareketler + fiziksel sayım
                    ↓
          reconcile_stock(...)
                    ↓
     Beklenen stok + farklar + sorunlar
```

Geçersiz veya mükerrer hareketler stok toplamına dahil edilmez; yapılandırılmış `ReconciliationIssue` kayıtları olarak döndürülür.

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
  reconciliation.py
tests/
  test_reconciliation.py
.github/workflows/
  python-ci.yml
```

## Yol haritası

1. CSV içe aktarma ve JSON rapor çıktısı
2. Raf/kat bazlı lokasyon desteği
3. Kritik stok ve sayım farkı önceliklendirmesi
4. Shopify/İkas/Sentos dışa aktarımlarına uyarlayıcılar
5. Basit web paneli

## Geliştirme notu

Bu proje yapay zekâ destekli geliştirme araçlarından yararlanılarak geliştirilmektedir. Mimari kararlar, iş kuralları, doğrulama ve yayın sorumluluğu proje sahibine aittir.

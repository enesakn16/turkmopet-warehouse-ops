# Türkmopet Warehouse Ops

Türkmopet depo hareketlerini doğrulayan, fiziksel sayım farklarını önceliklendiren ve bulunan sorunları atanabilir görevlere dönüştüren Python araçları.

## Özellikler

- Açılış stokları, hareketler, fiziksel sayım ve ürün konumu CSV dosyalarını okur.
- Mükerrer hareket, bilinmeyen SKU, geçersiz miktar, negatif stok, sayım farkı ve kritik stok sorunlarını yakalar.
- Sorunları `CRITICAL`, `HIGH`, `MEDIUM` ve `LOW` olarak sıralar.
- JSON raporu ve Excel uyumlu sorun CSV'si üretir.
- Aynı sorunu tekrar görevleştirmeden çalışan/ekip ataması ve çözüm geçmişi oluşturur.
- Görevleri SQLite üzerinde kalıcı saklar.
- Görev listeleme, atama, başlatma ve çözme işlemlerini komut satırından yönetir.

## Kurulum

```bash
python -m pip install -e .
```

## CSV şemaları

`opening.csv` ve opsiyonel `counted.csv`:

```csv
sku,quantity
TVS-JUPITER-FILTRE,10
```

`movements.csv`:

```csv
event_id,sku,movement_type,quantity
evt-1001,TVS-JUPITER-FILTRE,RECEIPT,5
```

Desteklenen hareket tipleri: `RECEIPT`, `SALE`, `RETURN`, `TRANSFER_OUT`, `ADJUSTMENT`.

Opsiyonel `metadata.csv`:

```csv
sku,floor,shelf,critical_stock
TVS-JUPITER-FILTRE,Zemin,A-12,5
```

## Stok mutabakatı komutu

```bash
warehouse-reconcile \
  --opening opening.csv \
  --movements movements.csv \
  --counted counted.csv \
  --metadata metadata.csv \
  --output reports/reconciliation.json \
  --issues-output reports/issues.csv
```

Çıkış kodları:

- `0`: stok dengeli
- `1`: inceleme gereken sorun var
- `2`: dosya veya şema hatası

Sorun CSV kolonları:

```text
severity,code,message,sku,event_id,location
```

## Görev yönetimi komutu

Varsayılan veritabanı `warehouse-tasks.db` dosyasıdır. Farklı bir dosya kullanmak için her komuta `--database <dosya>` eklenir.

Görevleri listele:

```bash
warehouse-tasks --database warehouse.db list
warehouse-tasks --database warehouse.db list --status OPEN
warehouse-tasks --database warehouse.db list --assignee Enes
```

Göreve çalışan ata:

```bash
warehouse-tasks --database warehouse.db assign <task_id> Enes
```

Görevi başlat:

```bash
warehouse-tasks --database warehouse.db start <task_id>
```

Görevi çözüm notuyla kapat:

```bash
warehouse-tasks --database warehouse.db resolve <task_id> \
  --note "Raf yeniden sayıldı ve stok düzeltildi."
```

Görev işlemlerinde başarı kodu `0`, bulunamayan görev veya geçersiz durum geçişinde hata kodu `2` döner.

## Görev yaşam döngüsü

```python
from warehouse_ops import assign_task, create_tasks, resolve_task, start_task

tasks = create_tasks(report)
task = assign_task(tasks[0], "Enes")
task = start_task(task)
task = resolve_task(task, "Raf tekrar sayıldı ve stok düzeltildi.")
```

Akış:

```text
OPEN -> IN_PROGRESS -> RESOLVED
```

Kurallar:

- Atanmamış görev başlatılamaz.
- Sadece açık görev başlatılabilir.
- Sadece devam eden görev çözülebilir.
- Çözüm notu zorunludur.
- Çözülmüş görev yeniden atanamaz.
- Aynı mutabakat sorunu ikinci bir görev üretmez.

## Python API

```python
from warehouse_ops import Movement, MovementType, ProductMetadata, reconcile_stock

report = reconcile_stock(
    opening_stock={"TVS-JUPITER-FILTRE": 10},
    movements=[Movement("evt-1001", "TVS-JUPITER-FILTRE", MovementType.RECEIPT, 5)],
    counted_stock={"TVS-JUPITER-FILTRE": 15},
    product_metadata={
        "TVS-JUPITER-FILTRE": ProductMetadata(floor="Zemin", shelf="A-12", critical_stock=5)
    },
)
```

## Geliştirme

```bash
python -m unittest discover -s tests -v
python -m compileall -q warehouse_ops tests
```

CI, Python 3.11, 3.12 ve 3.13 üzerinde çalışır.

## Proje yapısı

```text
warehouse_ops/
  cli.py
  io.py
  reconciliation.py
  service.py
  task_cli.py
  task_store.py
  tasks.py
tests/
  test_io.py
  test_reconciliation.py
  test_service.py
  test_task_cli.py
  test_task_store.py
  test_tasks.py
```

## Yol haritası

1. Stok mutabakatı ve görev senkronizasyonunu tek CLI komutunda birleştirme
2. Açık ve çözülmüş görevleri CSV olarak dışa aktarma
3. Shopify, İkas ve Sentos adaptörleri
4. Satır bazlı hata karantinası
5. Basit web paneli

## Geliştirme notu

Bu proje yapay zekâ destekli geliştirme araçlarından yararlanılarak geliştirilmektedir. Mimari kararlar, iş kuralları, doğrulama ve yayın sorumluluğu proje sahibine aittir.

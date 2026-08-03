# Otomatik görev yönlendirme

`warehouse-reconcile` komutu `--task-database` ile çalıştırıldığında yeni görevler sorumlu kuyruğa otomatik atanır.

## Varsayılan kurallar

| Sorun türü | Atanan kuyruk |
|---|---|
| Mükerrer hareket veya eksik hareket kimliği | `integration-team` |
| SKU, miktar, stok, sayım farkı ve kritik stok sorunları | `warehouse-operations` |
| Eşleşmeyen yeni sorun kodları | `operations-supervisor` |

`QUARANTINED_MOVEMENT_ROW` kayıtlarında doğrulama nedeni ayrıca incelenir. `event_id`, `event id` veya `duplicate` içeren nedenler entegrasyon ekibine; diğer karantina nedenleri depo operasyonuna atanır.

## Kuralları CSV ile değiştirme

Ekip veya çalışan adlarını kod değiştirmeden yönetmek için `--routing-config` kullanılır:

```bash
warehouse-reconcile \
  --opening opening.csv \
  --movements movements.csv \
  --counted counted.csv \
  --output reports/reconciliation.json \
  --task-database warehouse.db \
  --routing-config examples/task-routing.csv
```

CSV kolonları:

- `issue_code`: Sorun kodu. `*` güvenli varsayılan kuyruğu belirler.
- `assignee`: Atanacak çalışan veya ekip kuyruğu.
- `message_contains`: İsteğe bağlı, büyük-küçük harfe duyarsız mesaj filtresi.

Kurallar dosya sırasıyla değerlendirilir; ilk eşleşme kazanır. Bu nedenle mesaj filtresi olan özel kurallar, aynı sorun kodunun genel kuralından önce yazılmalıdır.

Eksik kolon, boş değer veya aynı sorun kodu + mesaj filtresinin tekrarı güvenli biçimde reddedilir. `--routing-config`, görev veritabanı olmadan kullanılamaz.

## Güvenli tekrar çalıştırma

Otomatik yönlendirme yalnızca ilk kez oluşturulan görevlere uygulanır. Aynı sorun sonraki mutabakatlarda tekrar görülürse mevcut görev korunur. Elle değiştirilmiş atama, görev durumu ve çözüm geçmişi üzerine yazılmaz.

Görevleri kuyruk bazında görmek için:

```bash
warehouse-tasks --database warehouse.db list --assignee integration-team
warehouse-tasks --database warehouse.db list --assignee warehouse-operations
warehouse-tasks --database warehouse.db list --assignee operations-supervisor
```

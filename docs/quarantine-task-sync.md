# Karantina satırlarını görevleştirme

`warehouse-reconcile`, `--movement-quarantine-output` ve `--task-database` birlikte kullanıldığında geçersiz hareket satırlarını yalnızca CSV'ye ayırmakla kalmaz; her satırı kalıcı ve atanabilir depo görevine dönüştürür.

```bash
warehouse-reconcile \
  --opening opening.csv \
  --movements movements.csv \
  --output reports/reconciliation.json \
  --movement-quarantine-output reports/movement-quarantine.csv \
  --task-database warehouse.db
```

Her karantina satırı `QUARANTINED_MOVEMENT_ROW` kodlu ve `HIGH` önem seviyeli bir görev üretir. Boş `event_id` bulunan satırlara `quarantine-row-<satır>` biçiminde kararlı bir kimlik atanır. Böylece aynı dosya tekrar işlendiğinde mükerrer görev oluşmaz; mevcut görev durumu, ataması ve çözüm geçmişi korunur.

Görev mesajında kaynak CSV satır numarası ve doğrulama hatası bulunur. Geçersiz satır stok hesabına katılmaz. Dosya başlığı eksikse satır karantinasına geçilmez; tüm içe aktarma güvenli biçimde durdurulur.

Görevleri listelemek ve atamak için:

```bash
warehouse-tasks --database warehouse.db list --status OPEN
warehouse-tasks --database warehouse.db assign <task_id> Enes
warehouse-tasks --database warehouse.db start <task_id>
warehouse-tasks --database warehouse.db resolve <task_id> \
  --note "Kaynak hareket düzeltildi ve dosya yeniden işlendi."
```

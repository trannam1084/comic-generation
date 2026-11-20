# Kaggle CLI và Experiment Artifacts — Task 08D

## 1. Trạng thái đã xác minh ngày 19/11/2026

CLI local là **Kaggle CLI 2.2.5**, Python 3.12.3, trong environment riêng `~/.venvs/kaggle-cli`. Executable là `~/.venvs/kaggle-cli/bin/kaggle`, hiện chưa có trên PATH. Không cài/nâng cấp package hoặc sửa shell configuration trong Task 08D/08D.1.

Chỉ kiểm tra sự tồn tại và mode của credential file: `~/.kaggle/access_token` tồn tại, mode 0600; không đọc/in/sao chép nội dung file. Không thấy legacy `~/.kaggle/kaggle.json` hoặc các biến authentication được set trong process kiểm tra. Authentication **đã hoạt động** với `kernels list --mine`, trả tài khoản `southernsea04`. Lượt mạng trong sandbox lỗi DNS; kiểm tra ngoài sandbox được cấp quyền đã thành công. Sandbox permission và Kaggle authentication là hai điều kiện khác nhau.

Task 08D.1 xác nhận lại version và authentication bằng một request `kernels list --mine --format json`: PASS, trả sáu notebook, gồm hai notebook liên quan bên dưới. Không chạy lại status/files/logs; bảng ghi nhận kết quả đã kiểm chứng ở Task 08D, không phải trạng thái live được refresh trong Task 08D.1.

| Notebook | Latest status qua CLI | Output files qua CLI | Logs |
|---|---|---|---|
| `southernsea04/05-qwen-structured-inference` | complete | 0 | Truy cập được, 7 dòng |
| `southernsea04/06-qwen-development-pilot` | error | 0 | Truy cập được, 42 dòng |

Không hiển thị/lưu log thô vào repository hoặc context; chỉ ghi nhận kết quả truy cập và số dòng. Chưa xác định nguyên nhân latest session của notebook 06 bị error. Không coi status này là bác bỏ kết quả pilot trong ZIP đã tải. CLI mặc định xem latest session; run ID của notebook, kernel version và session API là các định danh khác nhau, cần đối chiếu trước khi kết luận.

Nhóm trưởng đã chạy notebook thủ công trên Kaggle ở Task 08B/08C và tải các ZIP kết quả. Đây là manual notebook runs, không phải bằng chứng GPU execution qua CLI đã được kiểm chứng.

Không chạy actual `kernels push`, `kernels output`, quota query, GPU hoặc tải model trong Task 08D/08D.1. Help của các lệnh liên quan đã kiểm tra. Chưa kiểm chứng upload private, accelerator allocation hoặc CLI artifact download. Các lệnh ghi/upload ở phần dưới là hướng dẫn cho task sau, không phải hành động đã được phê duyệt ở Task 08D/08D.1.

## 2. CLI setup và authentication an toàn

Trong terminal VS Code có thể gọi executable bằng full path hoặc activate environment riêng:

```bash
source "$HOME/.venvs/kaggle-cli/bin/activate"
kaggle --version
kaggle kernels --help
```

Không dùng project `.venv` để cài GPU stack/CLI chung. Nếu một máy mới chưa có CLI, người dùng có thể cài riêng sau khi cho phép; các lệnh sau **chưa được thực thi** trong task này:

```bash
python3 -m venv "$HOME/.venvs/kaggle-cli"
"$HOME/.venvs/kaggle-cli/bin/python" -m pip install 'kaggle==2.2.5'
```

Theo [authentication documentation tại v2.2.5](https://github.com/Kaggle/kaggle-cli/blob/v2.2.5/docs/README.md#authentication), CLI hỗ trợ OAuth, API token file/environment và legacy credentials. Nếu cần xác thực lại, người dùng tự chạy interactive login trong terminal, không gửi token vào chat:

```bash
kaggle auth login
```

Giữ credential bên ngoài repository, chỉ account owner đọc được. Không gọi lệnh in access token; không dùng config dump, environment dump, shell tracing hoặc debug output có thể lộ credentials. Không đọc/copy credential files để chẩn đoán. Chỉ kiểm tra metadata file, trạng thái biến có/không và một request read-only được cho phép. Không đặt token trong notebook, kernel-metadata.json, CLI arguments, manifest hoặc URL.

Credentials để local CLI đăng nhập Kaggle khác với GitHub/Hugging Face Secrets mà notebook dùng trên Kaggle. Cấu hình/gắn Secrets qua Kaggle UI; không đưa giá trị Secrets vào metadata upload. Notebook 05/06 đã có các flag opt-in cho private repo/HF authentication.

## 3. Các commands read-only

Các lệnh dưới đây không upload hoặc khởi chạy notebook. Chỉ dùng trong phạm vi user cho phép, đúng account/kernel; không chuyển permission của read-only thành permission chạy GPU:

```bash
kaggle --version
kaggle kernels list --mine --format json
kaggle kernels status southernsea04/05-qwen-structured-inference
kaggle kernels files southernsea04/05-qwen-structured-inference --format json
kaggle kernels logs southernsea04/05-qwen-structured-inference
```

Có thể thay bằng slug notebook 06 đã xác minh. Nếu nhiều records, kiểm tra paging theo `--help`. Khi cần đối chiếu lịch sử, dùng `owner/kernel-slug/version` được CLI hỗ trợ; phải xác định version đúng, không đoán số version. Không dùng `logs --follow` như một vòng chờ vô hạn. Với automation, capture log trong process và chỉ xuất summary đã lọc; không chuyển nguyên log vào context hoặc file nếu chưa bảo đảm không có credentials.

Read-only command exit code 0 chỉ chứng minh request tương ứng thành công. `status=error` là trạng thái remote run, không phải lỗi authentication của lệnh status. Files rỗng không chứng minh artifacts chưa từng tồn tại trong interactive session hoặc run lịch sử.

## 4. Staging notebook và kernel-metadata.json

Chuẩn bị một upload directory riêng **bên ngoài repository**, chỉ gồm notebook đã review và metadata; không upload nguyên repository, Downloads, experiment storage hoặc `.venv`. Task 08D chưa tạo upload directory/metadata thật hoặc thay notebook baseline. Bản staging của một thực nghiệm mới cần có checksum riêng, không ghi đè notebook 02/05/06.

Ví dụ metadata cho một notebook **private**, mặc định chưa cho phép GPU/Internet:

```json
{
  "id": "YOUR_KAGGLE_USERNAME/qwen-next-development-run",
  "title": "Qwen Next Development Run",
  "code_file": "pilot.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": true,
  "enable_gpu": false,
  "enable_tpu": false,
  "enable_internet": false,
  "machine_shape": "",
  "dataset_sources": [],
  "competition_sources": [],
  "kernel_sources": [],
  "model_sources": []
}
```

Thay username/slug/file đúng với task đã review; code_file phải nằm trong upload directory. Không tự đặt `id_no` của notebook khác vì field này có thể được ưu tiên hơn id. `is_private` phải explicit true, không dựa vào default. Kiểm tra lại visibility trong Kaggle UI sau upload; private không thay thế review quyền sử dụng nội dung.

Theo help/source của **CLI 2.2.5**, upload mà **không execute** có thể dùng lệnh sau, nhưng vẫn phải được phê duyệt phạm vi upload trước khi thực thi:

```bash
kaggle kernels push -p /ABSOLUTE/APPROVED_UPLOAD_DIR --no-run
```

Task 08D không chạy lệnh này. `push` không có `--no-run` sẽ gửi một execution request; không dùng nó chỉ để "upload thử". CLI cũ có thể thiếu flag này: kiểm tra version/help, không bỏ flag rồi chạy để vượt lỗi. Không tự cập nhật notebook hoặc đổi visibility của notebook đã có.

## 5. Phê duyệt từng GPU run và accelerator

Trước **mỗi** GPU execution, cung cấp cho user bản review cụ thể: notebook/metadata SHA-256, full source commit, model revision, prompt version/hash, cases và số generations, decoding parameters, accelerator, timeout, Internet/data sources, output whitelist và quota dự kiến. Chỉ gửi execution sau khi user phê duyệt run đó; approval một run không bao gồm retry hoặc run kế tiếp.

Khi được phê duyệt, metadata của **bản staging mới** có thể bật GPU/Internet cho clone/model access. Không sửa baseline artifacts. CLI 2.2.5 hỗ trợ `--accelerator`, ví dụ minh họa lệnh execution **chưa được phép chạy trong Task 08D**:

```bash
kaggle kernels push -p /ABSOLUTE/APPROVED_UPLOAD_DIR --accelerator NvidiaTeslaT4 --timeout 900
```

`NvidiaTeslaT4` ở phiên bản này là accelerator T4 ×2, không phải cam kết session chỉ cấp một T4. Backend baseline vẫn dùng một `cuda:0`, FP16/batch 1, không auto device_map. Accelerator flag có thể override cấu hình GPU/TPU boolean; kiểm tra `machine_shape` và flag cùng nhau, không suy ra `enable_gpu=false` luôn vô hiệu hóa một accelerator explicit. Không dùng ID accelerator đã retired hoặc tự nhận replacement khác baseline.

Ghi model ID/revision và source commit cố định trong manifest, không chỉ branch động. Với baseline 08A–08C: source `390b069b9d5c4a83e97481580790760bf963efff`, model revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`, prompt `storyboard-v1.0-baseline-001`. Không tự đổi chúng để chạy qua lỗi.

Không tự retry failed/queued runs, không fallback sang accelerator/backend khác. Nếu request timeout mà chưa rõ remote đã tạo session hay chưa, kiểm tra status trước; không gửi execution request lại. Timeout là giới hạn yêu cầu, không phải bảo đảm quota/capacity hoặc GPU luôn được cấp.

## 6. Quota và giới hạn Kaggle API

CLI 2.2.5 có `kaggle quota` (đã kiểm tra help, chưa query quota thực tế). Trong task sau khi được phép kiểm tra read-only, dùng command này và Kaggle UI để xem GPU/TPU budget hiện tại. Không hard-code số giờ GPU/tuần hoặc lịch reset vì phụ thuộc account/platform.

Ước lượng budget trước run từ load time và số cases; ghi đây là ước lượng, không phải benchmark. Chọn timeout hữu hạn phù hợp, theo dõi status, không mở nhiều session chỉ để tranh GPU hoặc rerun sau hết quota. Nếu đang có session ngoài task, không tự cancel/xóa session đó. User quản lý dừng interactive session khi hoàn tất; `empty_cache` không tắt session hay hoàn lại quota.

Accelerator availability, quota, Internet, quyền truy cập private data/model và Secrets còn phụ thuộc account/session. CLI thành công không bảo đảm cell chạy thành công hoặc output hợp lệ. API không thay được mọi cấu hình Kaggle UI. Latest/versioned execution và interactive outputs có thể khác nhau; ghi kernel ref/version cùng notebook run/session ID khi đối chiếu artifacts.

## 7. Artifact download và hạn chế đã quan sát

Chưa có file nào được `kernels files` trả về cho hai notebook ở lượt kiểm tra Task 08D. Không chạy lại GPU để tạo bản thay thế. Khi cần download, trước hết xác định **đúng saved version** có ZIP; nếu API không thấy historical/interactive artifact, dùng ZIP user đã tải qua UI và ghi rõ provenance.

CLI 2.2.5 có file regex filter; ví dụ hướng dẫn cho task download được phê duyệt riêng:

```bash
kaggle kernels output OWNER/SLUG/VERSION -p /ABSOLUTE/NEW_DOWNLOAD_INBOX --file-pattern '(^|/)APPROVED_RUN_ID\.zip$'
```

Không dùng `--force`, không download vào repository hoặc ghi đè baseline storage. **Hạn chế source 2.2.5:** `kernels output` có thể tự ghi thêm kernel `.log` khi API trả log, ngay cả khi `--file-pattern` chỉ chọn ZIP. Vì vậy filter không phải bảo đảm download chỉ gồm ZIP. Nếu chưa bảo đảm logs không chứa credential hoặc cần strict ZIP-only retrieval, không chạy command này; tải đúng ZIP qua UI hoặc chờ adapter whitelist được review. Task 08D chưa triển khai adapter/download và chưa kiểm chứng download thành công.

Không đưa raw logs vào context hoặc archive baseline. Ghi notebook slug/version/download source ở record đi kèm, không tự đổi manifest gốc để chèn provenance mới.

## 8. Baseline experiment storage đã tạo

Root ngoài repository được gọi là `EXPERIMENT_ROOT`; ví dụ `../comic-generation-experiments/` khi đứng tại repository root. Đường dẫn tuyệt đối trên máy từng thành viên không cần đưa vào Git:

```text
EXPERIMENT_ROOT/
  task08b/
    20261118T212907Z-e405160e63.zip
    SHA256SUMS
    verification.json
  task08c/
    20261118T220702Z-31c52d49db.zip
    SHA256SUMS
    verification.json
```

Hai ZIP được copy từ `~/Downloads`, không move/xóa hoặc sửa bản gốc. Bản sao khớp source SHA-256:

| Task | ZIP SHA-256 | Internal checksums |
|---|---|---|
| 08B | `82bcc30f9f08e4c44e3344c5887eff03ab6941170afe41aa92479b1025a1a617` | 4/4 PASS |
| 08C | `0ab0112f400881cefdec1d0c86fbebe88dd102493d2058b46f3f1b4d97af1d22` | 16/16 PASS |

Đã kiểm tra CRC, duplicate member paths, absolute/traversal/Windows paths, symlink/encryption flags, archive size, member whitelist, checksum coverage và known-secret patterns trước copy. Không có member ngoài checksums manifest và chính checksums.json. Không giải nén, không chỉnh raw outputs; không phát hiện token pattern đã kiểm tra, nhưng pattern scan không phải bằng chứng tuyệt đối không có mọi loại secret.

verification.json ghi source/destination, checksum, counts, trạng thái copy và thời điểm UTC; không lưu credentials/raw logs. SHA256SUMS xác minh bản sao ZIP; checksums.json trong ZIP xác minh các artifacts bên trong. Checksum chứng minh byte integrity, không phải chữ ký xác thực tác giả/run hoặc semantic correctness. Không tự đồng nhất ZIP run ID với latest session đang có status trên API.

Task 08D.1 kiểm tra lại SHA-256 bản sao, bản gốc Downloads, SHA256SUMS và verification.json: đều khớp. Internal checksums đã đạt 4/4 và 16/16 ở Task 08D; archive hash không đổi nên không extract hoặc đọc lại mọi artifact để xác minh lặp không cần thiết. Không sửa các verification records gốc.

Nếu task sau cần extract: dùng directory mới, kiểm tra toàn bộ member names trước; từ chối absolute paths, `..`, backslash/drive paths, duplicates và symlinks; đặt giới hạn size/member count và bảo đảm destination resolve nằm dưới extract root. Không extract ghi đè, không sửa raw/manifest/checksums baseline. Các phân tích mới phải nằm trong output directory riêng, tham chiếu archive hash gốc.

## 9. Kaggle execution policy trong AGENTS.md

Task 08D.1 đã bổ sung policy ngắn vào [AGENTS.md](../AGENTS.md). Các nguyên tắc chính: user phê duyệt trước từng GPU run; không tự retry failed experiments, công khai/xóa notebook hoặc dataset, đọc/in/log credentials, sửa artifacts gốc hoặc commit weights/cache/credentials/ZIP. Chỉ chạy read-only commands trong phạm vi task được cho phép.

Quyền publish tài liệu qua Git không phải quyền upload notebook hoặc GPU execution trên Kaggle. Các command upload/execution trong tài liệu chỉ là hướng dẫn; một run tương lai cần phê duyệt riêng với nội dung và giới hạn cụ thể. Các checksums, run manifests và raw outputs gốc được giữ nguyên, phân tích mới lưu riêng.

## 10. Nguồn đối chiếu chính thức

- [CLI v2.2.5: setup/authentication](https://github.com/Kaggle/kaggle-cli/blob/v2.2.5/docs/README.md).
- [CLI v2.2.5: kernels commands/Secrets](https://github.com/Kaggle/kaggle-cli/blob/v2.2.5/docs/kernels.md).
- [CLI v2.2.5: metadata fields](https://github.com/Kaggle/kaggle-cli/blob/v2.2.5/docs/kernels_metadata.md).
- [Source v2.2.5](https://github.com/Kaggle/kaggle-cli/blob/v2.2.5/src/kaggle/api/kaggle_api_extended.py): kernels_push, kernels_output, kernels_status, kernels_logs.
- Help thực tế của executable local 2.2.5 là căn cứ cho flags được dùng. Không áp dụng ví dụ từ main/newer CLI nếu chưa đối chiếu version; source cho thấy một số defaults có thể khác mô tả docs, vì vậy metadata phải explicit.

# Hướng dẫn sử dụng phần Leader — Đồ án Socket P2P

## 1. Trạng thái hiện tại

**Đã viết và kiểm thử:** `protocol.py`, `tcp_chat.py`, `main.py`, `dev_console.py`, các bài test và tài liệu giao tiếp giữa module. Đây là phần TCP Core + Protocol + khung tích hợp của Leader.

**Chưa có, vì thuộc phần các thành viên khác:** `discovery.py` (UDP), `cli.py` (CLI không mất nội dung đang gõ), `file_transfer.py` (truyền file). Việc tích hợp tính năng cuối cùng, kiểm thử 2 máy, báo cáo và demo chỉ có thể hoàn tất **sau khi** các module này được triển khai. Không được quảng cáo phiên bản hiện tại là đủ 100 điểm.

## 2. Chạy trên MacBook

Mở **Terminal**, giải nén ZIP, vào folder dự án. Ví dụ:

```bash
cd ~/Downloads/lan_chat_leader
python3 --version
python3 -m unittest discover -s tests -v
```

Mở hai cửa sổ Terminal khác nhau. Terminal 1 chạy:

```bash
python3 main.py --name Alice --port 5001
```

Terminal 2 chạy:

```bash
python3 main.py --name Bob --port 5002
```

Ở Alice, nhập lần lượt:

```text
/connect 127.0.0.1:5002
/list
/chat Bob
Chào Bob!
```

Ở Bob, nhập:

```text
/list
/chat Alice
Chào Alice!
```

Sau đó mở Terminal 3:

```bash
python3 main.py --name Chi --port 5003
```

Ở Chi, chạy:

```text
/connect 127.0.0.1:5001
/chat Alice
Tin nhắn từ Chi
```

Nếu Alice đang chọn chat với Bob, Alice sẽ thấy thông báo từ Chi có `1 unread`. Khi Alice nhập `/chat Chi`, lịch sử tin từ Chi hiện lên và unread về 0. Dùng `/leave` để đóng socket chat hiện tại; `/quit` để dừng ứng dụng.

**Lưu ý:** Trong bản chạy thử, nhiều thread vẫn có thể in lên một dòng input đang gõ; đó là lý do thành viên 2 cần thay `dev_console.py` bằng `cli.py` với prompt redraw. `/list` hiện cũng chỉ hiển thị **TCP peers đã kết nối**, chưa phải người online qua UDP.

## 3. Vai trò từng file bạn sở hữu

- `protocol.py`: truyền header theo định dạng `4-byte length + UTF-8 JSON`; `receive_exact()` xử lý byte TCP đến không đủ hoặc bị chia gói; định nghĩa lỗi và giới hạn dữ liệu.
- `tcp_chat.py`: class `ChatNode`, mỗi peer có TCP acceptor; kết nối chủ động, thread nhận tin, đồng thời nhiều peer; message history; unread counter; đóng/reconnect, phản hồi lỗi; điểm gắn file handler.
- `main.py`: chọn tên/port, tạo ChatNode; tự nhận ra và nạp `discovery.py`, `cli.py`, `file_transfer.py` khi các thành viên đặt file đúng tên và đúng interface.
- `dev_console.py`: giao diện tạm phục vụ unit testing và demo thủ công TCP Core.
- `tests/`: kiểm tra message framing, Unicode, tin dài, 3 peers, unread, mất kết nối, kết nối đồng thời và định tuyến file-socket.

## 4. Phân biệt hai kiểu kết nối

Một chương trình `ChatNode` vừa lắng nghe TCP, vừa chủ động kết nối TCP. `HELLO` / `HELLO_ACK` là bắt tay ở **tầng ứng dụng**, không phải TCP three-way handshake của hệ điều hành. Khi nhận file, listener phân biệt `FILE_OFFER` ở frame đầu tiên và chuyển socket đó cho module File Transfer; chat vẫn dùng connection TCP khác.

`send_frame()` và `receive_frame()` chỉ xử lý **header**. Với MESSAGE, dữ liệu text mã hóa UTF-8 nằm ngay sau header, có độ dài đúng bằng trường `size`. Không được cho member 3 tự thay đổi format này khi chưa thống nhất.

## 5. Tự kiểm tra phần Leader trước khi giao việc

1. Chạy đủ 16 test `python3 -m unittest discover -s tests -v` — đều phải PASS.
2. Test 2 terminal, Alice -> Bob và Bob -> Alice thành công.
3. Test 3 terminal, khi Alice chọn Bob thì tin từ Chi tăng unread; mở Chi là đọc được lịch sử.
4. Test `/leave`, sau đó `/connect` để kết nối lại.
5. Chạy trên LAN thật (nếu có sẵn 2 máy): mỗi máy dùng **địa chỉ IP nội bộ** của máy kia, mở firewall cho port TCP tương ứng.
6. Đọc `docs/INTEGRATION_CONTRACT.md` để nắm được API phải yêu cầu hai thành viên làm theo.

## 6. Những điểm cần hiểu để bảo vệ trước giảng viên

**Vì sao UDP chỉ dùng discovery?** Broadcast và online/status chấp nhận mất vài thông báo vì phát lại sau 3 giây. Chat/file cần độ tin cậy và đúng thứ tự nên dùng TCP.

**Vì sao phải có message framing?** TCP là byte stream, không bảo đảm 1 lệnh `recv()` = 1 thông điệp. Bốn byte đầu xác định độ dài JSON header; với `MESSAGE`, trường `size` xác định chính xác độ dài payload UTF-8.

**Vì sao dùng thread?** TCP acceptor không được chặn việc nhận tin của từng peer. Mỗi kết nối chat có receiver thread; file sender tương lai chạy thread riêng.

**Vì sao có Lock?** History, unread counter, danh sách connections và active chat được các thread đọc/ghi đồng thời, nên cần khóa để tránh race condition.

**P2P khác central server thế nào?** Mỗi peer đều chạy một TCP listener. Không có server trung tâm lưu trữ/tự chuyển mọi tin. Người dùng A kết nối TCP trực tiếp tới B.

## 7. Những gì còn phải làm sau này

Thành viên 2 làm UDP và CLI, thành viên 3 làm file transfer. Sau đó bạn vẫn phải thực hiện **tích hợp cuối cùng, review PR, kiểm thử end-to-end trên ít nhất 2 máy, hoàn thiện README cuối và phối hợp báo cáo/ảnh Wireshark/demo**. Đây là công việc phụ thuộc vào kết quả của hai thành viên, không thể đánh dấu hoàn thành ngay bây giờ.

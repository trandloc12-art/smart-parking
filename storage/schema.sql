-- Chạy được nhiều lần (idempotent). Database.init_schema() tự chạy file này, tách theo dòng "GO".
-- Mỗi khối GO là một batch riêng: cột vừa thêm chỉ được dùng ở batch SAU.

-- 1) Bảng thẻ được phép sử dụng (danh sách trắng)
IF OBJECT_ID(N'dbo.cards', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cards (
        card_uid   NVARCHAR(32) NOT NULL CONSTRAINT PK_cards PRIMARY KEY,   -- HEX viết hoa, không dấu cách
        is_active  BIT          NOT NULL CONSTRAINT DF_cards_active DEFAULT 1,
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_cards_created DEFAULT SYSDATETIME()
    );
END
GO

-- 2) Nạp sẵn 3 thẻ (bỏ qua thẻ đã có)
INSERT INTO dbo.cards (card_uid)
SELECT v.uid
FROM (VALUES (N'AB1992CA'), (N'DB2B11CA'), (N'1B12E1CB')) AS v(uid)
WHERE NOT EXISTS (SELECT 1 FROM dbo.cards c WHERE c.card_uid = v.uid);
GO

-- 3) Bảng lượt gửi xe: cổng vào ghi time_in, cổng ra ghi time_out + fee
IF OBJECT_ID(N'dbo.access_log', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.access_log (
        id            INT IDENTITY(1,1) CONSTRAINT PK_access_log PRIMARY KEY,
        card_uid      NVARCHAR(32)  NOT NULL
                      CONSTRAINT FK_access_log_card REFERENCES dbo.cards(card_uid),
        plate_number  NVARCHAR(10)  NULL,       -- đúng 5 số lúc VÀO
        plate_full    NVARCHAR(20)  NULL,       -- biển đầy đủ OCR đọc được (chỉ để tham khảo)
        image_in      NVARCHAR(260) NULL,       -- ảnh lúc vào (thư mục anh_chup)
        time_in       DATETIME2(0)  NOT NULL CONSTRAINT DF_access_log_time_in DEFAULT SYSDATETIME(),
        time_out      DATETIME2(0)  NULL,       -- NULL = xe còn trong bãi
        fee           INT           NULL        -- tiền (VND), NULL cho đến khi xe ra
    );
END
GO

-- 4) Nâng cấp bảng từ các phiên bản cũ (giữ nguyên dữ liệu)
IF COL_LENGTH(N'dbo.access_log', N'created_at') IS NOT NULL
   AND COL_LENGTH(N'dbo.access_log', N'time_in') IS NULL
    EXEC sp_rename N'dbo.access_log.created_at', N'time_in', N'COLUMN';
GO
IF COL_LENGTH(N'dbo.access_log', N'image_path') IS NOT NULL
   AND COL_LENGTH(N'dbo.access_log', N'image_in') IS NULL
    EXEC sp_rename N'dbo.access_log.image_path', N'image_in', N'COLUMN';
GO
IF COL_LENGTH(N'dbo.access_log', N'time_out') IS NULL ALTER TABLE dbo.access_log ADD time_out DATETIME2(0) NULL;
IF COL_LENGTH(N'dbo.access_log', N'fee') IS NULL      ALTER TABLE dbo.access_log ADD fee INT NULL;
GO

-- 5) Cột mới cho cổng ra / đối chiếu / bỏ phiếu 5 ảnh
IF COL_LENGTH(N'dbo.access_log', N'plate_out')    IS NULL ALTER TABLE dbo.access_log ADD plate_out    NVARCHAR(10)  NULL;  -- 5 số lúc RA
IF COL_LENGTH(N'dbo.access_log', N'image_out')    IS NULL ALTER TABLE dbo.access_log ADD image_out    NVARCHAR(260) NULL;
IF COL_LENGTH(N'dbo.access_log', N'match_status') IS NULL ALTER TABLE dbo.access_log ADD match_status NVARCHAR(20)  NULL;  -- MATCH / APPROVED_CLOSE / APPROVED_MISMATCH
IF COL_LENGTH(N'dbo.access_log', N'override_note') IS NULL ALTER TABLE dbo.access_log ADD override_note NVARCHAR(200) NULL; -- lý do nhân viên cho qua
IF COL_LENGTH(N'dbo.access_log', N'votes_in')     IS NULL ALTER TABLE dbo.access_log ADD votes_in     NVARCHAR(100) NULL;  -- VD "25888:3,25883:1"
IF COL_LENGTH(N'dbo.access_log', N'votes_out')    IS NULL ALTER TABLE dbo.access_log ADD votes_out    NVARCHAR(100) NULL;
IF COL_LENGTH(N'dbo.access_log', N'gate_in')      IS NULL ALTER TABLE dbo.access_log ADD gate_in      NVARCHAR(10)  NULL;
IF COL_LENGTH(N'dbo.access_log', N'gate_out')     IS NULL ALTER TABLE dbo.access_log ADD gate_out     NVARCHAR(10)  NULL;
GO

-- 6) Ràng buộc: biển số mới phải đúng 5 chữ số. WITH NOCHECK -> dữ liệu cũ không bị kiểm tra lại.
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints
               WHERE name = N'CK_access_log_plate_in' AND parent_object_id = OBJECT_ID(N'dbo.access_log'))
    ALTER TABLE dbo.access_log WITH NOCHECK
        ADD CONSTRAINT CK_access_log_plate_in CHECK (plate_number LIKE N'[0-9][0-9][0-9][0-9][0-9]');
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints
               WHERE name = N'CK_access_log_plate_out' AND parent_object_id = OBJECT_ID(N'dbo.access_log'))
    ALTER TABLE dbo.access_log WITH NOCHECK
        ADD CONSTRAINT CK_access_log_plate_out CHECK (plate_out LIKE N'[0-9][0-9][0-9][0-9][0-9]');
GO

-- 7) Chỉ mục
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_access_log_card_open'
               AND object_id = OBJECT_ID(N'dbo.access_log'))
    CREATE INDEX IX_access_log_card_open ON dbo.access_log (card_uid, time_out);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_access_log_time_in'
               AND object_id = OBJECT_ID(N'dbo.access_log'))
    CREATE INDEX IX_access_log_time_in ON dbo.access_log (time_in DESC);
GO

-- 8) Mỗi thẻ chỉ được có MỘT lượt đang mở (chặn 2 cổng/2 lần quẹt tạo lượt trùng).
--    Nếu dữ liệu cũ đã có thẻ bị trùng lượt mở thì bỏ qua và cảnh báo; hãy đóng bớt lượt rồi chạy lại.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_access_log_open_card'
               AND object_id = OBJECT_ID(N'dbo.access_log'))
BEGIN
    IF EXISTS (SELECT 1 FROM dbo.access_log WHERE time_out IS NULL GROUP BY card_uid HAVING COUNT(*) > 1)
    BEGIN
        PRINT N'CANH BAO: co the dang co nhieu luot mo cho cung mot the; chua tao UX_access_log_open_card.'
    END
    ELSE
    BEGIN
        CREATE UNIQUE INDEX UX_access_log_open_card ON dbo.access_log (card_uid) WHERE time_out IS NULL
    END
END
GO

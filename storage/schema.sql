-- Chạy được nhiều lần (idempotent). Database.init_schema() tự chạy file này, tách theo dòng "GO".

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

-- 3) Bảng lượt gửi xe: quẹt lần 1 = vào (time_in), quẹt lần 2 = ra (time_out + fee)
IF OBJECT_ID(N'dbo.access_log', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.access_log (
        id           INT IDENTITY(1,1) CONSTRAINT PK_access_log PRIMARY KEY,
        card_uid     NVARCHAR(32)  NOT NULL
                     CONSTRAINT FK_access_log_card REFERENCES dbo.cards(card_uid),
        plate_number NVARCHAR(10)  NULL,       -- 5 số ở dòng dưới biển
        plate_full   NVARCHAR(20)  NULL,       -- biển số đầy đủ (nếu đọc được)
        image_path   NVARCHAR(260) NULL,       -- ảnh lúc vào (trong thư mục anh_chup)
        time_in      DATETIME2(0)  NOT NULL CONSTRAINT DF_access_log_time_in DEFAULT SYSDATETIME(),
        time_out     DATETIME2(0)  NULL,       -- NULL = xe còn trong bãi
        fee          INT           NULL        -- tiền (VND), NULL cho đến khi xe ra
    );
END
GO

-- 4) Nâng cấp bảng cũ (nếu trước đó đã chạy bản chưa có giờ ra / giá tiền)
IF COL_LENGTH(N'dbo.access_log', N'created_at') IS NOT NULL
   AND COL_LENGTH(N'dbo.access_log', N'time_in') IS NULL
    EXEC sp_rename N'dbo.access_log.created_at', N'time_in', N'COLUMN';
GO
IF COL_LENGTH(N'dbo.access_log', N'time_out') IS NULL ALTER TABLE dbo.access_log ADD time_out DATETIME2(0) NULL;
IF COL_LENGTH(N'dbo.access_log', N'fee') IS NULL      ALTER TABLE dbo.access_log ADD fee INT NULL;
GO

-- 5) Chỉ mục
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_access_log_card_open'
               AND object_id = OBJECT_ID(N'dbo.access_log'))
    CREATE INDEX IX_access_log_card_open ON dbo.access_log (card_uid, time_out);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_access_log_time_in'
               AND object_id = OBJECT_ID(N'dbo.access_log'))
    CREATE INDEX IX_access_log_time_in ON dbo.access_log (time_in DESC);
GO

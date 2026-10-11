-- 查询指定公众号的文章，每个公众号只取一篇
-- 按创建时间倒序排列，获取最新的文章

WITH
    RankedArticles AS (
        SELECT
            id,
            title,
            url,
            account_name,
            created_at,
            summary,
            content,
            pdf_path,
            ROW_NUMBER() OVER (
                PARTITION BY
                    account_name
                ORDER BY created_at DESC
            ) as rn
        FROM wechat_articles
        WHERE
            account_name IN (
                '集微网',
                '未来半导体',
                '半导体行业联盟',
                'AR圈',
                'c114通信网',
                'cioe中国光博会',
                '手机技术资讯',
                'CINNO',
                '通信产业网',
                '维深Wellsenn XR',
                'CIC集成电路',
                'VR陀螺',
                '讯石光通信',
                '量子前哨',
                '高通中国',
                '华为中国',
                'Big-Bit商务委',
                '莫界科技',
                '高工智能汽车',
                'NE时代新能源',
                '中汽数据',
                '高工锂电',
                '智汇光伏',
                'A股投资日历',
                '鱼与塘',
                '盘前纪要',
                '盘盘的投研笔记',
                '核心逻辑社',
                '热点投研',
                '调研纪要',
                '韭研公社',
                '东昌路打工人',
                '主流和龙妖',
                '奥KA姆剃刀',
                '增的逻辑',
                '逻辑挖掘社',
                '纪要投研',
                '可研可填',
                '美投investing',
                '小熊跑得快',
                'Lee话',
                '刘翔科技研究',
                '蓝猫研究所',
                '信息平权',
                '计墨式',
                '证监会发布',
                '晨明的策略深度思考',
                '驰策论市',
                '新股必读',
                '人形机器人发布',
                '渾水調研',
                '老罗的暗中观察'
            )
            AND url IS NOT NULL -- 确保有URL
            AND url != '' -- 确保URL不为空
    )
SELECT id, title, url, account_name
FROM RankedArticles
WHERE
    rn = 1 -- 每个公众号只取一篇
ORDER BY account_name;
-- 按公众号名称排序
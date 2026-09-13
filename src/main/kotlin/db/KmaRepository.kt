package db

import kma.ForecastZoneRecord
import kma.MidTermForecastRecord
import kma.RegionLocationRecord
import kma.ShortTermForecastRecord
import kma.WarningZoneRecord
import org.jetbrains.exposed.v1.core.eq
import org.jetbrains.exposed.v1.jdbc.selectAll
import org.jetbrains.exposed.v1.jdbc.transactions.transaction
import org.slf4j.LoggerFactory
import java.sql.Timestamp
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

object KmaRepository {

    private val log = LoggerFactory.getLogger(KmaRepository::class.java)
    private val DT_FORMATTER = DateTimeFormatter.ofPattern("yyyyMMddHHmm")

    private fun parseIsoOrCustom(dtStr: String): Timestamp {
        return try {
            val clean = dtStr.replace("[- :TZ]".toRegex(), "")
            val ldt = when (clean.length) {
                8 -> LocalDate.parse(clean, DateTimeFormatter.ofPattern("yyyyMMdd")).atStartOfDay()
                10 -> LocalDateTime.parse(clean + "00", DT_FORMATTER)
                12 -> LocalDateTime.parse(clean, DT_FORMATTER)
                14 -> LocalDateTime.parse(clean.substring(0, 12), DT_FORMATTER)
                else -> LocalDateTime.now(ZoneId.of("Asia/Seoul"))
            }
            Timestamp.valueOf(ldt)
        } catch (e: Exception) {
            Timestamp.valueOf(LocalDateTime.now(ZoneId.of("Asia/Seoul")))
        }
    }

    /**
     * weather_provider 마스터 기본 레코드 초기화 (KMA)
     */
    fun initProvider() {
        val sql = """
            INSERT INTO weather_provider (provider_code, provider_name, api_base_url, is_active)
            VALUES ('KMA', '기상청 API 허브', 'https://apihub.kma.go.kr', TRUE)
            ON CONFLICT (provider_code) DO NOTHING
        """.trimIndent()
        try {
            DbConfig.dataSource.connection.use { conn ->
                conn.createStatement().use { stmt ->
                    stmt.execute(sql)
                }
            }
        } catch (e: Exception) {
            log.warn("weather_provider 초기화 확인 중 예외 (이미 존재하거나 무시 가능): {}", e.message)
        }
    }

    /**
     * 예보구역 마스터 목록 저장 (Bulk Upsert)
     */
    fun saveForecastZones(zones: List<ForecastZoneRecord>) {
        if (zones.isEmpty()) return
        initProvider()

        val sql = """
            INSERT INTO forecast_zone (
                reg_id, provider_code, reg_name, reg_en, reg_up, reg_sp,
                lat, lon, stn_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (reg_id) DO UPDATE SET
                provider_code = EXCLUDED.provider_code,
                reg_name = EXCLUDED.reg_name,
                reg_en = EXCLUDED.reg_en,
                reg_up = EXCLUDED.reg_up,
                reg_sp = EXCLUDED.reg_sp,
                lat = EXCLUDED.lat,
                lon = EXCLUDED.lon,
                stn_id = EXCLUDED.stn_id,
                updated_at = CURRENT_TIMESTAMP
        """.trimIndent()

        DbConfig.dataSource.connection.use { conn ->
            conn.autoCommit = false
            try {
                conn.prepareStatement(sql).use { ps ->
                    for (z in zones) {
                        ps.setString(1, z.regId)
                        ps.setString(2, z.providerCode)
                        ps.setString(3, z.regName)
                        ps.setString(4, z.regEn)
                        ps.setString(5, z.regUp)
                        ps.setString(6, z.regSp)
                        if (z.lat != null) ps.setDouble(7, z.lat) else ps.setNull(7, java.sql.Types.NUMERIC)
                        if (z.lon != null) ps.setDouble(8, z.lon) else ps.setNull(8, java.sql.Types.NUMERIC)
                        if (z.stnId != null) ps.setInt(9, z.stnId) else ps.setNull(9, java.sql.Types.INTEGER)
                        ps.addBatch()
                    }
                    ps.executeBatch()
                }
                conn.commit()
                log.info("✅ 예보구역 마스터 {}건 저장/갱신 완료", zones.size)
            } catch (e: Exception) {
                conn.rollback()
                log.error("❌ 예보구역 마스터 저장 실패", e)
                throw e
            }
        }
    }

    /**
     * 특보구역 마스터 목록 저장 (Bulk Upsert)
     */
    fun saveWarningZones(zones: List<WarningZoneRecord>) {
        if (zones.isEmpty()) return
        initProvider()

        val sql = """
            INSERT INTO warning_zone (
                wrn_zone_cd, provider_code, wrn_zone_name, created_at, updated_at
            ) VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (wrn_zone_cd) DO UPDATE SET
                provider_code = EXCLUDED.provider_code,
                wrn_zone_name = EXCLUDED.wrn_zone_name,
                updated_at = CURRENT_TIMESTAMP
        """.trimIndent()

        DbConfig.dataSource.connection.use { conn ->
            conn.autoCommit = false
            try {
                conn.prepareStatement(sql).use { ps ->
                    for (z in zones) {
                        ps.setString(1, z.wrnZoneCd)
                        ps.setString(2, z.providerCode)
                        ps.setString(3, z.wrnZoneName)
                        ps.addBatch()
                    }
                    ps.executeBatch()
                }
                conn.commit()
                log.info("✅ 특보구역 마스터 {}건 저장/갱신 완료", zones.size)
            } catch (e: Exception) {
                conn.rollback()
                log.error("❌ 특보구역 마스터 저장 실패", e)
                throw e
            }
        }
    }

    /**
     * 행정동 마스터 목록 저장 (Bulk Upsert)
     */
    fun saveRegions(regions: List<RegionLocationRecord>) {
        if (regions.isEmpty()) return

        val sql = """
            INSERT INTO region_location (
                region_code, provider_code, reg_id, wrn_zone_cd, sido, sigungu, eupmyeondong,
                nx, ny, mid_ta_reg_id, mid_land_reg_id, is_active, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (region_code) DO UPDATE SET
                sido = EXCLUDED.sido,
                sigungu = EXCLUDED.sigungu,
                eupmyeondong = EXCLUDED.eupmyeondong,
                nx = EXCLUDED.nx,
                ny = EXCLUDED.ny,
                mid_ta_reg_id = EXCLUDED.mid_ta_reg_id,
                mid_land_reg_id = EXCLUDED.mid_land_reg_id,
                is_active = EXCLUDED.is_active,
                updated_at = CURRENT_TIMESTAMP
        """.trimIndent()

        DbConfig.dataSource.connection.use { conn ->
            conn.autoCommit = false
            try {
                conn.prepareStatement(sql).use { ps ->
                    for (r in regions) {
                        ps.setString(1, r.regionCode)
                        ps.setString(2, r.providerCode)
                        ps.setString(3, r.regId)
                        ps.setString(4, r.wrnZoneCd)
                        ps.setString(5, r.sido)
                        ps.setString(6, r.sigungu)
                        ps.setString(7, r.eupmyeondong)
                        ps.setInt(8, r.nx)
                        ps.setInt(9, r.ny)
                        ps.setString(10, r.midTaRegId)
                        ps.setString(11, r.midLandRegId)
                        ps.setBoolean(12, r.isActive)
                        ps.addBatch()
                    }
                    ps.executeBatch()
                }
                conn.commit()
                log.info("✅ 행정동 마스터 {}건 저장/갱신 완료", regions.size)
            } catch (e: Exception) {
                conn.rollback()
                log.error("❌ 행정동 마스터 저장 실패", e)
                throw e
            }
        }
    }

    /**
     * 활성화된 행정동 전체 목록 조회
     */
    fun getActiveRegions(): List<RegionLocationRecord> {
        return transaction(DbConfig.database) {
            RegionLocationTable.selectAll()
                .where { RegionLocationTable.isActive eq true }
                .map { row ->
                    RegionLocationRecord(
                        regionCode = row[RegionLocationTable.regionCode],
                        providerCode = row[RegionLocationTable.providerCode],
                        regId = row[RegionLocationTable.regId],
                        wrnZoneCd = row[RegionLocationTable.wrnZoneCd],
                        sido = row[RegionLocationTable.sido],
                        sigungu = row[RegionLocationTable.sigungu],
                        eupmyeondong = row[RegionLocationTable.eupmyeondong],
                        nx = row[RegionLocationTable.nx],
                        ny = row[RegionLocationTable.ny],
                        midTaRegId = row[RegionLocationTable.midTaRegId],
                        midLandRegId = row[RegionLocationTable.midLandRegId],
                        isActive = row[RegionLocationTable.isActive]
                    )
                }
        }
    }

    /**
     * 단기예보 일괄 저장 (Bulk Upsert: provider_code + region_code + fcst_datetime 기준 자동 갱신)
     */
    fun saveShortTermForecasts(forecasts: List<ShortTermForecastRecord>) {
        if (forecasts.isEmpty()) return

        val sql = """
            INSERT INTO short_term_forecast (
                region_code, provider_code, base_datetime, fcst_datetime,
                temp, sky, pty, pop, pcp, reh, wsd, vec,
                version, created_at, updated_at, last_collected_at
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?,
                1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (provider_code, region_code, fcst_datetime) DO UPDATE SET
                base_datetime = EXCLUDED.base_datetime,
                temp = EXCLUDED.temp,
                sky = EXCLUDED.sky,
                pty = EXCLUDED.pty,
                pop = EXCLUDED.pop,
                pcp = EXCLUDED.pcp,
                reh = EXCLUDED.reh,
                wsd = EXCLUDED.wsd,
                vec = EXCLUDED.vec,
                version = CASE
                    WHEN short_term_forecast.temp IS DISTINCT FROM EXCLUDED.temp
                      OR short_term_forecast.sky IS DISTINCT FROM EXCLUDED.sky
                      OR short_term_forecast.pty IS DISTINCT FROM EXCLUDED.pty
                      OR short_term_forecast.pop IS DISTINCT FROM EXCLUDED.pop
                      OR short_term_forecast.pcp IS DISTINCT FROM EXCLUDED.pcp
                      OR short_term_forecast.reh IS DISTINCT FROM EXCLUDED.reh
                    THEN short_term_forecast.version + 1
                    ELSE short_term_forecast.version
                END,
                updated_at = CASE
                    WHEN short_term_forecast.temp IS DISTINCT FROM EXCLUDED.temp
                      OR short_term_forecast.sky IS DISTINCT FROM EXCLUDED.sky
                      OR short_term_forecast.pty IS DISTINCT FROM EXCLUDED.pty
                      OR short_term_forecast.pop IS DISTINCT FROM EXCLUDED.pop
                      OR short_term_forecast.pcp IS DISTINCT FROM EXCLUDED.pcp
                      OR short_term_forecast.reh IS DISTINCT FROM EXCLUDED.reh
                    THEN CURRENT_TIMESTAMP
                    ELSE short_term_forecast.updated_at
                END,
                last_collected_at = CURRENT_TIMESTAMP
        """.trimIndent()

        DbConfig.dataSource.connection.use { conn ->
            conn.autoCommit = false
            try {
                conn.prepareStatement(sql).use { ps ->
                    for (f in forecasts) {
                        ps.setString(1, f.regionCode)
                        ps.setString(2, f.providerCode)
                        ps.setTimestamp(3, parseIsoOrCustom(f.baseDatetime))
                        ps.setTimestamp(4, parseIsoOrCustom(f.fcstDatetime))

                        if (f.temp != null) ps.setDouble(5, f.temp) else ps.setNull(5, java.sql.Types.NUMERIC)
                        ps.setString(6, f.sky)
                        ps.setString(7, f.pty)
                        if (f.pop != null) ps.setInt(8, f.pop) else ps.setNull(8, java.sql.Types.SMALLINT)
                        ps.setString(9, f.pcp)
                        if (f.pop != null && f.reh != null) ps.setInt(10, f.reh) else ps.setNull(10, java.sql.Types.SMALLINT)
                        if (f.wsd != null) ps.setDouble(11, f.wsd) else ps.setNull(11, java.sql.Types.NUMERIC)
                        if (f.vec != null) ps.setInt(12, f.vec) else ps.setNull(12, java.sql.Types.SMALLINT)

                        ps.addBatch()
                    }
                    ps.executeBatch()
                }
                conn.commit()
                log.info("✅ 단기예보 레코드 {}건 저장/갱신 완료", forecasts.size)
            } catch (e: Exception) {
                conn.rollback()
                log.error("❌ 단기예보 저장 실패", e)
                throw e
            }
        }
    }

    /**
     * 중기예보 일괄 저장 (Bulk Upsert: provider_code + mid_ta_reg_id + fcst_date 기준 자동 갱신)
     */
    fun saveMidTermForecasts(forecasts: List<MidTermForecastRecord>) {
        if (forecasts.isEmpty()) return

        val sql = """
            INSERT INTO mid_term_forecast (
                mid_ta_reg_id, mid_land_reg_id, provider_code, base_datetime, fcst_date,
                min_temp, max_temp, wf_am, wf_pm, pop_am, pop_pm,
                version, created_at, updated_at, last_collected_at
            ) VALUES (
                ?, ?, ?, ?, ?::DATE,
                ?, ?, ?, ?, ?, ?,
                1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (provider_code, mid_ta_reg_id, fcst_date) DO UPDATE SET
                mid_land_reg_id = EXCLUDED.mid_land_reg_id,
                base_datetime = EXCLUDED.base_datetime,
                min_temp = EXCLUDED.min_temp,
                max_temp = EXCLUDED.max_temp,
                wf_am = EXCLUDED.wf_am,
                wf_pm = EXCLUDED.wf_pm,
                pop_am = EXCLUDED.pop_am,
                pop_pm = EXCLUDED.pop_pm,
                version = CASE
                    WHEN mid_term_forecast.min_temp IS DISTINCT FROM EXCLUDED.min_temp
                      OR mid_term_forecast.max_temp IS DISTINCT FROM EXCLUDED.max_temp
                      OR mid_term_forecast.wf_am IS DISTINCT FROM EXCLUDED.wf_am
                      OR mid_term_forecast.wf_pm IS DISTINCT FROM EXCLUDED.wf_pm
                      OR mid_term_forecast.pop_am IS DISTINCT FROM EXCLUDED.pop_am
                      OR mid_term_forecast.pop_pm IS DISTINCT FROM EXCLUDED.pop_pm
                    THEN mid_term_forecast.version + 1
                    ELSE mid_term_forecast.version
                END,
                updated_at = CASE
                    WHEN mid_term_forecast.min_temp IS DISTINCT FROM EXCLUDED.min_temp
                      OR mid_term_forecast.max_temp IS DISTINCT FROM EXCLUDED.max_temp
                      OR mid_term_forecast.wf_am IS DISTINCT FROM EXCLUDED.wf_am
                      OR mid_term_forecast.wf_pm IS DISTINCT FROM EXCLUDED.wf_pm
                      OR mid_term_forecast.pop_am IS DISTINCT FROM EXCLUDED.pop_am
                      OR mid_term_forecast.pop_pm IS DISTINCT FROM EXCLUDED.pop_pm
                    THEN CURRENT_TIMESTAMP
                    ELSE mid_term_forecast.updated_at
                END,
                last_collected_at = CURRENT_TIMESTAMP
        """.trimIndent()

        DbConfig.dataSource.connection.use { conn ->
            conn.autoCommit = false
            try {
                conn.prepareStatement(sql).use { ps ->
                    for (f in forecasts) {
                        ps.setString(1, f.midTaRegId)
                        ps.setString(2, f.midLandRegId)
                        ps.setString(3, f.providerCode)
                        ps.setTimestamp(4, parseIsoOrCustom(f.baseDatetime))
                        // format fcstDate to YYYY-MM-DD
                        val cleanDate = f.fcstDate.replace("-", "")
                        val formattedDate = if (cleanDate.length == 8) {
                            "${cleanDate.substring(0, 4)}-${cleanDate.substring(4, 6)}-${cleanDate.substring(6, 8)}"
                        } else {
                            f.fcstDate
                        }
                        ps.setString(5, formattedDate)

                        if (f.minTemp != null) ps.setDouble(6, f.minTemp) else ps.setNull(6, java.sql.Types.NUMERIC)
                        if (f.maxTemp != null) ps.setDouble(7, f.maxTemp) else ps.setNull(7, java.sql.Types.NUMERIC)
                        ps.setString(8, f.wfAm)
                        ps.setString(9, f.wfPm)
                        if (f.popAm != null) ps.setInt(10, f.popAm) else ps.setNull(10, java.sql.Types.SMALLINT)
                        if (f.popPm != null) ps.setInt(11, f.popPm) else ps.setNull(11, java.sql.Types.SMALLINT)

                        ps.addBatch()
                    }
                    ps.executeBatch()
                }
                conn.commit()
                log.info("✅ 중기예보 레코드 {}건 저장/갱신 완료", forecasts.size)
            } catch (e: Exception) {
                conn.rollback()
                log.error("❌ 중기예보 저장 실패", e)
                throw e
            }
        }
    }
}

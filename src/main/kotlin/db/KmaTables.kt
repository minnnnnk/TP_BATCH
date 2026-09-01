package db

import org.jetbrains.exposed.v1.core.dao.id.LongIdTable
import org.jetbrains.exposed.v1.core.Table

/**
 * 1) weather_provider (기관 마스터)
 */
object WeatherProviderTable : Table("weather_provider") {
    val providerCode = varchar("provider_code", 20)
    val providerName = varchar("provider_name", 50)
    val apiBaseUrl = varchar("api_base_url", 255).nullable()
    val isActive = bool("is_active").default(true)
    val createdAt = varchar("created_at", 50).nullable()
    val updatedAt = varchar("updated_at", 50).nullable()

    override val primaryKey = PrimaryKey(providerCode)
}

/**
 * 2) forecast_zone (예보구역 마스터)
 */
object ForecastZoneTable : Table("forecast_zone") {
    val regId = varchar("reg_id", 20)
    val providerCode = varchar("provider_code", 20).references(WeatherProviderTable.providerCode)
    val regName = varchar("reg_name", 50)
    val regEn = varchar("reg_en", 100).nullable()
    val regUp = varchar("reg_up", 20).nullable()
    val regSp = varchar("reg_sp", 10).nullable()
    val lat = double("lat").nullable()
    val lon = double("lon").nullable()
    val stnId = integer("stn_id").nullable()
    val createdAt = varchar("created_at", 50).nullable()
    val updatedAt = varchar("updated_at", 50).nullable()

    override val primaryKey = PrimaryKey(regId)
}

/**
 * 3) warning_zone (특보구역 마스터)
 */
object WarningZoneTable : Table("warning_zone") {
    val wrnZoneCd = varchar("wrn_zone_cd", 20)
    val providerCode = varchar("provider_code", 20).references(WeatherProviderTable.providerCode)
    val wrnZoneName = varchar("wrn_zone_name", 50)
    val createdAt = varchar("created_at", 50).nullable()
    val updatedAt = varchar("updated_at", 50).nullable()

    override val primaryKey = PrimaryKey(wrnZoneCd)
}

/**
 * 4) region_location (행정동 지역 마스터)
 */
object RegionLocationTable : Table("region_location") {
    val regionCode = varchar("region_code", 10)
    val providerCode = varchar("provider_code", 20).references(WeatherProviderTable.providerCode)
    val regId = varchar("reg_id", 20).nullable()
    val wrnZoneCd = varchar("wrn_zone_cd", 20).nullable()
    val sido = varchar("sido", 50)
    val sigungu = varchar("sigungu", 50).nullable()
    val eupmyeondong = varchar("eupmyeondong", 50).nullable()
    val nx = integer("nx")
    val ny = integer("ny")
    val midTaRegId = varchar("mid_ta_reg_id", 20)
    val midLandRegId = varchar("mid_land_reg_id", 20)
    val isActive = bool("is_active").default(true)
    val createdAt = varchar("created_at", 50).nullable()
    val updatedAt = varchar("updated_at", 50).nullable()

    override val primaryKey = PrimaryKey(regionCode)
}

/**
 * 5) short_term_forecast (단기예보 - 최신 갱신형)
 */
object ShortTermForecastTable : LongIdTable("short_term_forecast") {
    val regionCode = varchar("region_code", 10).references(RegionLocationTable.regionCode)
    val providerCode = varchar("provider_code", 20).references(WeatherProviderTable.providerCode)
    val baseDatetime = varchar("base_datetime", 50)
    val fcstDatetime = varchar("fcst_datetime", 50)
    val temp = double("temp").nullable()
    val sky = varchar("sky", 20).nullable()
    val pty = varchar("pty", 20).nullable()
    val pop = integer("pop").nullable()
    val pcp = varchar("pcp", 20).nullable()
    val reh = integer("reh").nullable()
    val wsd = double("wsd").nullable()
    val vec = integer("vec").nullable()
    val version = integer("version").default(1)
    val createdAt = varchar("created_at", 50).nullable()
    val updatedAt = varchar("updated_at", 50).nullable()
    val lastCollectedAt = varchar("last_collected_at", 50).nullable()
}

/**
 * 6) mid_term_forecast (중기예보 - 최신 갱신형)
 */
object MidTermForecastTable : LongIdTable("mid_term_forecast") {
    val midTaRegId = varchar("mid_ta_reg_id", 20)
    val midLandRegId = varchar("mid_land_reg_id", 20)
    val providerCode = varchar("provider_code", 20).references(WeatherProviderTable.providerCode)
    val baseDatetime = varchar("base_datetime", 50)
    val fcstDate = varchar("fcst_date", 20)
    val minTemp = double("min_temp").nullable()
    val maxTemp = double("max_temp").nullable()
    val wfAm = varchar("wf_am", 50).nullable()
    val wfPm = varchar("wf_pm", 50).nullable()
    val popAm = integer("pop_am").nullable()
    val popPm = integer("pop_pm").nullable()
    val version = integer("version").default(1)
    val createdAt = varchar("created_at", 50).nullable()
    val updatedAt = varchar("updated_at", 50).nullable()
    val lastCollectedAt = varchar("last_collected_at", 50).nullable()
}

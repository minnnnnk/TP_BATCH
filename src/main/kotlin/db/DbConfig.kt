package db

import com.zaxxer.hikari.HikariConfig
import com.zaxxer.hikari.HikariDataSource
import org.jetbrains.exposed.v1.jdbc.Database
import java.io.File
import java.util.Properties

object DbConfig {

    private val props: Properties by lazy {
        Properties().apply {
            val secretsFile = File("secrets.properties")
            if (secretsFile.exists()) secretsFile.inputStream().use { load(it) }
        }
    }

    private fun value(envKey: String, propKey: String): String {
        System.getenv(envKey)?.takeIf { it.isNotBlank() }?.let { return it }
        return props.getProperty(propKey)
            ?.takeIf { it.isNotBlank() }
            ?: error("DB 설정을 찾을 수 없습니다: $propKey (환경변수 $envKey 또는 secrets.properties 확인)")
    }

    private val host get() = value("DB_HOST", "db.host")
    private val port get() = value("DB_PORT", "db.port")
    private val name get() = value("DB_NAME", "db.name")
    private val user get() = value("DB_USER", "db.user")
    private val password get() = value("DB_PASSWORD", "db.password")

    val dataSource: HikariDataSource by lazy {
        val config = HikariConfig().apply {
            jdbcUrl = "jdbc:postgresql://$host:$port/$name"
            username = user
            password = this@DbConfig.password
            driverClassName = "org.postgresql.Driver"
            maximumPoolSize = 5
        }
        HikariDataSource(config)
    }

    val database: Database by lazy { Database.connect(dataSource) }
}

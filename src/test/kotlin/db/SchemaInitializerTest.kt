package db

import org.junit.jupiter.api.Test
import java.io.File
import kotlin.test.assertTrue

class SchemaInitializerTest {

    @Test
    fun `initialize kma schema`() {
        val schemaFile = File("src/main/resources/schema-kma.sql")
        assertTrue(schemaFile.exists(), "schema-kma.sql must exist")

        val sqlScript = schemaFile.readText()

        DbConfig.dataSource.connection.use { conn ->
            conn.createStatement().use { stmt ->
                stmt.execute(sqlScript)
                println("✅ KMA Database Schema (tables, constraints, indexes) successfully created/verified in aidb!")
            }
        }
    }
}

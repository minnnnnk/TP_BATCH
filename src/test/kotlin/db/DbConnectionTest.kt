package db

import org.jetbrains.exposed.v1.jdbc.transactions.transaction
import org.junit.jupiter.api.Test
import kotlin.test.assertTrue

class DbConnectionTest {

    @Test
    fun testDbConnection() {
        transaction(DbConfig.database) {
            val connection = connection
            println("Connected to database successfully: ${connection.catalog ?: "PostgreSQL"}")
            assertTrue(!connection.isClosed)
        }
    }
}

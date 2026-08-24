package app

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication

@SpringBootApplication(scanBasePackages = ["app", "batch", "db", "tourapi"])
class Application

fun main(args: Array<String>) {
    runApplication<Application>(*args)
}

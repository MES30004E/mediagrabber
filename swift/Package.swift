// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MorganBackendClient",
    platforms: [.macOS(.v12)],
    products: [.library(name: "MorganBackendClient", targets: ["MorganBackendClient"])],
    targets: [
        .target(name: "MorganBackendClient"),
        .testTarget(name: "MorganBackendClientTests", dependencies: ["MorganBackendClient"],
                    resources: [.copy("Fixtures")])
    ]
)

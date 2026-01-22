package main

import (
	"context"
	"fmt"

	"github.com/kelseyhightower/envconfig"
	"maunium.net/go/mautrix"
	"maunium.net/go/mautrix/id"
)

type Specification struct {
	RoomID      string `envconfig:"MATRIX_ROOM_ID" required:"true"`
	UserID      string `envconfig:"MATRIX_USER_ID" required:"true"`
	AccessToken string `envconfig:"MATRIX_ACCESS_TOKEN" required:"true"`
	Server      string `envconfig:"MATRIX_SERVER" required:"true"`
	Message     string `envconfig:"MATRIX_DAILY_MESSAGE" default:"Hello! This is a simple automated message."`
}

func main() {
	// 1. Load configuration from environment variables
	var spec Specification
	err := envconfig.Process("", &spec)
	if err != nil {
		panic(err)
	}

	// 2. Setup Matrix client parameters
	homeserver := spec.Server
	userID := id.UserID(spec.UserID)
	accessToken := spec.AccessToken
	roomID := id.RoomID(spec.RoomID)

	// 3. Create the client
	client, err := mautrix.NewClient(homeserver, userID, accessToken)
	if err != nil {
		panic(err)
	}

	// 4. Send the message
	_, err = client.SendText(context.Background(), roomID, spec.Message)
	if err != nil {
		fmt.Printf("Error sending message: %v\n", err)
		return
	}

	fmt.Println("Message sent successfully!")
}
